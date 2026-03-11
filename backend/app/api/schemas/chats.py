from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatCreate(BaseModel):
    title: str | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ChatListResponse(BaseModel):
    items: list[ChatResponse]


class ChatRecentItem(BaseModel):
    thread_id: uuid.UUID
    title: str
    project_id: uuid.UUID
    project_name: str
    updated_at: datetime


class ChatRecentResponse(BaseModel):
    items: list[ChatRecentItem]


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None


class ChatDetailResponse(BaseModel):
    thread_id: uuid.UUID
    title: str
    messages: list[MessageOut]
