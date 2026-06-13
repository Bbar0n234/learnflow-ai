from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.api.schemas.artifacts import ArtifactListItem
from app.api.schemas.common import Page


class ChatCreate(BaseModel):
    title: str | None = None


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


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None
    artifacts: list[ArtifactListItem] = []
    trace_id: str | None = None
    feedback_score: bool | None = None
    redacted: bool = False


class ChatDetailResponse(BaseModel):
    thread_id: uuid.UUID
    title: str
    security_blocked: bool = False
    messages: list[MessageOut]
