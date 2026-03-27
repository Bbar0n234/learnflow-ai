from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import structlog

from app.models.thread_view import ThreadView
from app.repositories.artifact import ArtifactRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import AgentRunner, Message, StreamEvent
from app.services.exceptions import EntityNotFoundError

logger = structlog.get_logger()


@dataclass
class ChatDetail:
    """ThreadView + message history from checkpointer."""

    thread_view: ThreadView
    messages: list[Message]


class ChatService:
    def __init__(
        self,
        *,
        thread_view_repo: ThreadViewRepository,
        agent_runner: AgentRunner,
        artifact_repo: ArtifactRepository,
    ) -> None:
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner
        self._artifact_repo = artifact_repo

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
        return ChatDetail(thread_view=thread_view, messages=messages)

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

        async for event in self._agent_runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=project_id,
            user_id=user_id,
        ):
            if event.type == "artifact_created":
                artifact_ids.append(event.data["id"])
            if event.type == "error":
                had_error = True
            yield event

        # error and done are mutually exclusive terminal events (SSE contract).
        # If runner already emitted error — skip post-hoc and don't emit done.
        if had_error:
            return

        # Post-hoc: link artifacts to final message
        message_id: str | None = None
        try:
            if artifact_ids:
                message_id = await self._agent_runner.get_last_ai_message_id(
                    thread_id=thread_id
                )
                if message_id:
                    await self._artifact_repo.set_message_id(
                        [uuid.UUID(aid) for aid in artifact_ids],
                        message_id,
                    )
        except Exception:
            # Post-hoc linking failure is non-critical:
            # artifacts remain linked to thread_id, just without message_id.
            logger.warning(
                "post-hoc artifact linking failed",
                thread_id=str(thread_id),
                exc_info=True,
            )

        yield StreamEvent(type="done", data={"message_id": message_id or ""})

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return await self._agent_runner.cancel(thread_id=thread_id)
