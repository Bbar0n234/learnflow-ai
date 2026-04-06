from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InstructionsResponse(BaseModel):
    content: str


class InstructionsUpdate(BaseModel):
    content: str = Field(max_length=5000)


class MemoryItem(BaseModel):
    key: str
    description: str
    content: str
    created_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryItem]
