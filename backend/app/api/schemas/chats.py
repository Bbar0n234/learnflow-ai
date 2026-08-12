from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import Page
from app.services.constants import MAX_TITLE_LENGTH


class ChatUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    security_blocked: bool = False


class ChatListResponse(Page[ChatResponse]):
    pass


class ChatRecentItem(BaseModel):
    thread_id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    updated_at: datetime
    security_blocked: bool = False


class ChatRecentResponse(Page[ChatRecentItem]):
    pass


class ReasoningPartOut(BaseModel):
    """Reasoning span of an assistant turn (design-brief § «Модель typed parts»)."""

    type: Literal["reasoning"] = "reasoning"
    content: str


class TextPartOut(BaseModel):
    """The assistant turn's final text."""

    type: Literal["text"] = "text"
    content: str


class ToolCallPartOut(BaseModel):
    """One tool call of an assistant turn, paired with its result."""

    type: Literal["tool_call"] = "tool_call"
    call_id: str
    tool: str
    args: str
    args_truncated: bool
    status: Literal["success", "error", "pending"]
    result_preview: str
    result_truncated: bool


class ArtifactDiffOut(BaseModel):
    """Compact added/removed line counters for a text-file update."""

    added: int
    removed: int


class ArtifactPartOut(BaseModel):
    """One artifact write/update surfaced by a tool call (design-brief § «Артефакты»).

    ``type`` is the union discriminator (``"artifact"``); the file's own type
    (extension) is ``artifact_type`` — kept separate so it can never collide
    with the discriminator, same reasoning as the SSE envelope's ``artifact_type``
    remap (``stream_events.py``). ``ArtifactPart.path`` carries a real
    workspace-relative path for ``write_file`` (T1.3); ``generate_image``
    (still PG-backed until T1.7) carries its PG id here instead.
    """

    type: Literal["artifact"] = "artifact"
    path: str
    title: str
    artifact_type: str
    kind: Literal["created", "updated"]
    diff: ArtifactDiffOut | None = None


MessagePartOut = Annotated[
    ReasoningPartOut | TextPartOut | ToolCallPartOut | ArtifactPartOut,
    Field(discriminator="type"),
]


class AttachmentOut(BaseModel):
    """One user-attached file surfaced on a user message (design-brief § «Вложения пользователя»).

    Symmetric with ``ArtifactPartOut``'s path+title pair on the output side:
    the UI renders a chip from this, not by parsing the model-facing note out
    of ``content``.
    """

    path: str
    title: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None
    trace_id: str | None = None
    feedback_score: bool | None = None
    redacted: bool = False
    parts: list[MessagePartOut] = []
    attachments: list[AttachmentOut] = []


class ChatDetailResponse(BaseModel):
    thread_id: uuid.UUID
    title: str
    security_blocked: bool = False
    messages: list[MessageOut]
