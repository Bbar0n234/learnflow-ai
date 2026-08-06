from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    # Annotation-only: runtime-импорт замыкает цикл app.services ↔ app.agent
    # (agent.runner импортирует Message/StreamEvent отсюда).
    from app.agent.config import ResolvedModelConfig


@dataclass(frozen=True)
class StreamEvent:
    """SSE event from agent stream. Mapping to wire format is in API Layer."""

    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ReasoningPart:
    """One reasoning span of an assistant turn (``AIMessage.additional_kwargs["reasoning"]``)."""

    content: str
    type: Literal["reasoning"] = "reasoning"


@dataclass(frozen=True)
class TextPart:
    """The assistant turn's final text (``AIMessage.content``)."""

    content: str
    type: Literal["text"] = "text"


@dataclass(frozen=True)
class ToolCallPart:
    """One tool call of an assistant turn: ``AIMessage.tool_calls`` entry + paired ``ToolMessage``.

    ``status`` is ``"pending"`` when the turn was cut short before the paired
    ``ToolMessage`` was produced (checkpoint ends mid tool-call) — the wire
    contract (``tool_result``) only ever carries ``success``/``error`` because
    a live stream always eventually resolves or the run ends; the persisted
    history can freeze in that in-between state.

    ``args`` and ``result_preview`` are truncated independently, so each carries
    its own flag — same as the live wire, where ``tool_call_args`` and
    ``tool_result`` are separate events with separate ``truncated``.
    """

    call_id: str
    tool: str
    args: str
    args_truncated: bool
    status: Literal["success", "error", "pending"]
    result_preview: str
    result_truncated: bool
    type: Literal["tool_call"] = "tool_call"


Part = ReasoningPart | TextPart | ToolCallPart


@dataclass(frozen=True)
class Message:
    """Message from chat history (from checkpointer)."""

    id: str
    role: str
    content: str
    created_at: datetime | None = None
    redacted: bool = False
    parts: list[Part] = field(default_factory=list)


class AgentRunner(Protocol):
    def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        session: AsyncSession | None = None,
        model_config: ResolvedModelConfig | None = None,
    ) -> AsyncIterator[StreamEvent]: ...

    async def get_history(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> list[Message]: ...

    async def get_last_ai_message_id(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> str | None: ...

    async def cancel(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> bool: ...

    async def delete_thread(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> None: ...
