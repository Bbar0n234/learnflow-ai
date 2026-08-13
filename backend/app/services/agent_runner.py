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


@dataclass(frozen=True)
class ArtifactPart:
    """One artifact write/update a tool call produced (``ToolMessage.artifact`` element).

    Reconstructed by ``checkpoint_history`` on replay, one per element of the
    list ``content_and_artifact`` carries (design-brief § «Артефакты»: a job
    touching N files -> N parts). ``kind`` distinguishes a fresh write from an
    overwrite of an existing path — the SSE event type (``artifact_created`` /
    ``artifact_updated``) already made that call live; here it survives as data
    since a single ``ArtifactPart`` type covers both in the history union.

    ``type`` is the file extension without the leading dot (``"md"``, ``"png"``,
    ...), *not* a discriminator literal like the sibling ``Part`` dataclasses'
    ``type`` field — the API layer's ``ArtifactPartOut`` renames it to
    ``artifact_type`` so it never collides with that schema's own ``"artifact"``
    discriminator.
    """

    path: str
    title: str
    type: str
    kind: Literal["created", "updated"]
    diff: dict[str, int] | None = None


Part = ReasoningPart | TextPart | ToolCallPart | ArtifactPart


@dataclass(frozen=True)
class AttachmentRef:
    """One user-attached file referenced by a ``HumanMessage`` (design-brief § «Вложения пользователя»).

    Mirrors ``ArtifactPart``'s path+title pair on the input side. The model
    sees these paths baked into a note appended to ``HumanMessage.content``
    (``prompt_builder.render_attachment_note``); the UI renders a chip from
    this list instead — reconstructed by ``checkpoint_history`` from
    ``HumanMessage.additional_kwargs["attachments"]`` on replay, so the note
    text is never re-parsed to find them.
    """

    path: str
    title: str


@dataclass(frozen=True)
class Message:
    """Message from chat history (from checkpointer)."""

    id: str
    role: str
    content: str
    created_at: datetime | None = None
    redacted: bool = False
    parts: list[Part] = field(default_factory=list)
    attachments: list[AttachmentRef] = field(default_factory=list)


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
        attachments: list[str] | None = None,
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
