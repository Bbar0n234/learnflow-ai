from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArtifactListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    type: str
    created_at: datetime


class ArtifactListResponse(BaseModel):
    items: list[ArtifactListItem]


class ArtifactDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    type: str
    content: str
    thread_id: uuid.UUID | None
    message_id: str | None = None
    created_at: datetime
