from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import Page
from app.services.constants import MAX_TITLE_LENGTH


class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: str = Field(max_length=MAX_TITLE_LENGTH)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(Page[ProjectResponse]):
    pass
