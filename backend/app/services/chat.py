from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.models.thread_view import ThreadView
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import AgentRunner, Message, StreamEvent
from app.services.exceptions import EntityNotFoundError


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
    ) -> None:
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner

    async def create_chat(self, *, project_id: uuid.UUID, title: str) -> ThreadView:
        return await self._thread_view_repo.create(project_id=project_id, title=title)

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
        async for event in self._agent_runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=project_id,
            user_id=user_id,
        ):
            yield event

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return await self._agent_runner.cancel(thread_id=thread_id)
