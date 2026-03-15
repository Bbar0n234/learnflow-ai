from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class StreamEvent:
    """SSE event from agent stream. Mapping to wire format is in API Layer."""

    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class Message:
    """Message from chat history (from checkpointer)."""

    id: str
    role: str
    content: str
    created_at: datetime | None = None


class AgentRunner(Protocol):
    def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[StreamEvent]: ...

    async def get_history(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> list[Message]: ...

    async def cancel(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> bool: ...
