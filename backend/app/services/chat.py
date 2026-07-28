from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.repositories.mcp_server import MCPServerRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import AgentRunner, Message, StreamEvent
from app.services.chat_title import ChatTitleGenerator
from app.services.constants import DEFAULT_CHAT_TITLE
from app.services.exceptions import EntityNotFoundError
from app.storage.trace_store import TraceStore

logger = structlog.get_logger()

# Events that carry no verdict about the pre-graph USER_INPUT security check,
# and so must not be read as "the guard let this run through" by the auto-title
# trigger below. ``stream_started`` is unconditionally the first event of every
# run (agent/runner.py) and ``heartbeat`` fills any silence — both are emitted
# *before* the check can have produced ``security_block``. Deciding on the
# literal first event, as the pre-v2 contract allowed, would hand blocked input
# straight to the title LLM.
_TITLE_GUARD_NEUTRAL_TYPES = frozenset({"stream_started", "heartbeat"})


@dataclass
class ChatDetail:
    """ThreadView + message history from checkpointer."""

    thread_view: ThreadView
    messages: list[Message]
    trace_ids: dict[str, str] = field(default_factory=dict)
    feedback_scores: dict[str, bool] = field(default_factory=dict)


class ChatService:
    def __init__(
        self,
        *,
        thread_view_repo: ThreadViewRepository,
        agent_runner: AgentRunner,
        artifact_repo: ArtifactRepository,
        trace_store: TraceStore | None = None,
        session: AsyncSession | None = None,
        title_generator: ChatTitleGenerator | None = None,
    ) -> None:
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner
        self._artifact_repo = artifact_repo
        self._trace_store = trace_store
        self._session = session
        self._title_generator = title_generator

    def _require_session(self, operation: str) -> AsyncSession:
        """The session for an operation that cannot be expressed without one.

        ``session`` is optional on the constructor for the sociable-unit test
        form (fake repos, no DB), and most methods degrade to "the caller's
        session commits later". Writes whose effect must be complete before
        the method returns cannot: raising here keeps a missing session a
        loud wiring error instead of a silently skipped half of the work.
        """
        if self._session is None:
            raise RuntimeError(f"ChatService.{operation} requires a DB session")
        return self._session

    async def create_chat(self, *, project_id: uuid.UUID) -> ThreadView:
        thread_view = await self._thread_view_repo.create(
            project_id=project_id, title=DEFAULT_CHAT_TITLE
        )
        # Commit before returning — clients may issue the next request
        # (POST /messages) before FastAPI's yield-dependency commits at the end
        # of the response cycle, which races against the message route's own
        # session reading thread_views.
        if self._session is not None:
            await self._session.commit()
            await self._session.refresh(thread_view)
        logger.info(
            "chat created",
            thread_id=str(thread_view.thread_id),
            project_id=str(project_id),
        )
        return thread_view

    async def rename_chat(self, thread_id: uuid.UUID, *, title: str) -> ThreadView:
        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        updated = await self._thread_view_repo.update(thread_view, title=title)
        # Commit before returning, same rule as create_chat above
        # (conventions/db.md § DB-сессии и commit): the client refetches the
        # chat lists straight off this response, and those GETs run in their
        # own sessions — a commit deferred to the end of the response cycle
        # lets them read the old title back.
        if self._session is not None:
            await self._session.commit()
        logger.info("chat renamed", thread_id=str(thread_id))
        return updated

    async def get_thread_view(self, thread_id: uuid.UUID) -> ThreadView:
        """Raw ``ThreadView`` fetch, no history/trace assembly.

        Used by the DELETE route (routes/chats.py) to resolve ownership
        manually — mirrors ``ProjectService.get_project`` used the same way by
        ``delete_project`` — and by ``delete_chat`` below as its own
        defense-in-depth existence check.
        """
        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        return thread_view

    async def delete_chat(self, thread_id: uuid.UUID) -> None:
        """Delete a chat with its full cascade.

        Order matters (design-brief § Rename и delete): the DB-side transaction
        (polymorphic disables cleanup + row delete + commit) runs first and is
        the source of truth; the LangGraph checkpoint cleanup runs after, as a
        best-effort side effect. The checkpointer has its own connection pool
        and can't join this transaction — if it fails, the worst case is
        orphaned checkpoints (the same class of garbage that already exists
        today), never a "deleted chat with intact history" inconsistency.

        The cascade is unconditional, so a session is required: skipping the
        polymorphic-disables cleanup would leave dangling scope rows behind a
        log line that reads like success. Existence is resolved first — the
        not-found contract the route turns into an idempotent 204 outranks a
        wiring error.
        """
        thread_view = await self.get_thread_view(thread_id)
        session = self._require_session("delete_chat")

        await MCPServerRepository(session).cleanup_disables_for_thread(thread_id)
        await self._thread_view_repo.delete(thread_view)
        await session.commit()
        logger.info("chat deleted", thread_id=str(thread_id))

        try:
            await self._agent_runner.delete_thread(thread_id=thread_id)
        except Exception:
            logger.warning(
                "checkpoint thread deletion failed",
                thread_id=str(thread_id),
                exc_info=True,
            )

    async def list_chats(
        self, project_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[ThreadView], int]:
        items = await self._thread_view_repo.list_by_project(
            project_id, limit=limit, offset=offset
        )
        total = await self._thread_view_repo.count_by_project(project_id)
        return items, total

    async def get_chat(self, thread_id: uuid.UUID) -> ChatDetail:
        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        messages = await self._agent_runner.get_history(thread_id=thread_id)

        trace_ids: dict[str, str] = {}
        feedback_scores: dict[str, bool] = {}
        if self._trace_store:
            try:
                trace_ids = await self._trace_store.get_by_thread(thread_id)
            except Exception:
                logger.warning(
                    "trace_ids read from redis failed",
                    thread_id=str(thread_id),
                    exc_info=True,
                )
            if trace_ids:
                try:
                    feedback_scores = await self._trace_store.get_feedback_batch(
                        list(trace_ids.values())
                    )
                except Exception:
                    logger.warning(
                        "feedback scores read from redis failed",
                        thread_id=str(thread_id),
                        exc_info=True,
                    )

        return ChatDetail(
            thread_view=thread_view,
            messages=messages,
            trace_ids=trace_ids,
            feedback_scores=feedback_scores,
        )

    async def list_recent(
        self, user_id: uuid.UUID, *, limit: int = 10, offset: int = 0
    ) -> tuple[list[ThreadView], int]:
        items = await self._thread_view_repo.list_recent(
            user_id, limit=limit, offset=offset
        )
        total = await self._thread_view_repo.count_by_user(user_id)
        return items, total

    async def send_message(
        self,
        *,
        thread_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        """Stream agent response.

        IMPORTANT for API Layer (feat-005): this is an async generator —
        the body executes lazily on first __anext__(), not at call time.
        API must pre-validate chat existence BEFORE creating StreamingResponse
        to return a clean 404 instead of an error inside an already-opened stream.
        Validation here is defense in depth.
        """

        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        await self._thread_view_repo.touch(thread_view)
        # Commit the touch before the relay loop starts (conventions/db.md
        # § DB-сессии и commit, same rule as create_chat above). ``touch`` is an
        # UPDATE on the chat's own ``thread_views`` row, and ``get_db_session``
        # commits only after the SSE generator is exhausted — so an uncommitted
        # touch keeps a row lock for the entire stream, and the background
        # auto-title task (its own session) blocks on that very row: the title
        # write can never land inside the stream, and on a run longer than
        # ``DB_STATEMENT_TIMEOUT_SECONDS`` it is killed outright and the title is
        # lost. Everything pending in this session at this point is read-only
        # (auth user, project, thread lookups), so the precondition of the rule
        # holds — no write that should have been rolled back gets fixed by this
        # commit. ``expire_on_commit=False`` (infra/db.py) keeps ``thread_view``
        # readable below.
        if self._session is not None:
            await self._session.commit()

        artifact_ids: list[str] = []
        stream_ended_without_done = False
        trace_id = ""

        # Auto-title (design-brief § Доставка title): trigger is "title still
        # the placeholder". Binding the generator to a local (None when this
        # run must not generate) is what makes the trigger and the call site
        # one and the same condition. The generation task is started on the
        # first agent event that clears the security guard — that is, the first
        # event outside ``_TITLE_GUARD_NEUTRAL_TYPES``, and never when that
        # event is itself security_block (blocked input never reaches the title
        # LLM). ``title_task`` is polled between agent events below; a
        # ready, non-empty result is forwarded as a title_updated event exactly
        # once per run, then the handle is dropped — never after a terminal
        # event (see the poll site).
        title_generator = (
            self._title_generator if thread_view.title == DEFAULT_CHAT_TITLE else None
        )
        guard_checked = False
        title_task: asyncio.Task[str | None] | None = None

        async for event in self._agent_runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=project_id,
            user_id=user_id,
            session=self._session,
        ):
            if event.type == "trace_id":
                trace_id = event.data.get("trace_id", "")
                continue
            if event.type == "artifact_created":
                artifact_ids.append(event.data["id"])
            if event.type in ("error", "security_block", "cancelled"):
                stream_ended_without_done = True

            if (
                title_generator is not None
                and not guard_checked
                and event.type not in _TITLE_GUARD_NEUTRAL_TYPES
            ):
                guard_checked = True
                if event.type != "security_block":
                    title_task = title_generator.generate_title(thread_id, content)

            yield event

            # ``error``/``security_block``/``cancelled`` are terminal: the
            # stream closes on them and nothing may follow (streaming.md
            # § Protocol Overview), so a title that finished in the window
            # before a terminal event is dropped from the stream — the task
            # still writes it to the DB and the client picks it up on its next
            # refetch (design-brief § Доставка title, fallback).
            if stream_ended_without_done:
                continue

            if title_task is not None and title_task.done():
                # A cancelled task carries no title, only a CancelledError that
                # ``.result()`` would raise straight into this SSE generator
                # (``ChatTitleGenerator._run``'s barrier catches Exception, and
                # CancelledError is a BaseException). Shutdown cancels the whole
                # registry, so the run losing its title here is exactly the
                # "generation did not make it" case — treat it as such.
                title = None if title_task.cancelled() else title_task.result()
                title_task = None
                if title:
                    yield StreamEvent(type="title_updated", data={"title": title})

        # error/security_block/cancelled and done are mutually exclusive
        # terminal events (SSE contract). If the runner already emitted one of
        # them — skip post-hoc and don't emit done.
        if stream_ended_without_done:
            return

        # Post-hoc: resolve message_id + link artifacts
        message_id: str | None = None
        try:
            message_id = await self._agent_runner.get_last_ai_message_id(
                thread_id=thread_id
            )
            if message_id and artifact_ids:
                await self._artifact_repo.set_message_id(
                    [uuid.UUID(aid) for aid in artifact_ids],
                    message_id,
                )
        except Exception:
            logger.warning(
                "post-hoc message resolution failed",
                thread_id=str(thread_id),
                exc_info=True,
            )

        if self._trace_store and trace_id and message_id:
            try:
                await self._trace_store.save(thread_id, message_id, trace_id)
            except Exception:
                logger.warning(
                    "trace_id save to redis failed",
                    thread_id=str(thread_id),
                    exc_info=True,
                )

        yield StreamEvent(
            type="done",
            data={"message_id": message_id or "", "trace_id": trace_id},
        )

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return await self._agent_runner.cancel(thread_id=thread_id)
