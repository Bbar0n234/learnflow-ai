from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import structlog

from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.repositories.thread_view import ThreadViewRepository
from app.repositories.trace_store import TraceStore
from app.services.agent_runner import AgentRunner, Message, StreamEvent
from app.services.exceptions import EntityNotFoundError

logger = structlog.get_logger()


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
    ) -> None:
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner
        self._artifact_repo = artifact_repo
        self._trace_store = trace_store

    async def create_chat(self, *, project_id: uuid.UUID, title: str) -> ThreadView:
        thread_view = await self._thread_view_repo.create(
            project_id=project_id, title=title
        )
        logger.info(
            "chat created",
            thread_id=str(thread_view.thread_id),
            project_id=str(project_id),
        )
        return thread_view

    async def list_chats(self, project_id: uuid.UUID) -> list[ThreadView]:
        return await self._thread_view_repo.list_by_project(project_id)

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
        self, user_id: uuid.UUID, *, limit: int = 10
    ) -> list[ThreadView]:
        return await self._thread_view_repo.list_recent(user_id, limit=limit)

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

        artifact_ids: list[str] = []
        had_error = False
        trace_id = ""

        async for event in self._agent_runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=project_id,
            user_id=user_id,
        ):
            if event.type == "trace_id":
                trace_id = event.data.get("trace_id", "")
                continue
            if event.type == "artifact_created":
                artifact_ids.append(event.data["id"])
            if event.type == "error":
                had_error = True
            yield event

        # error and done are mutually exclusive terminal events (SSE contract).
        # If runner already emitted error — skip post-hoc and don't emit done.
        if had_error:
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
