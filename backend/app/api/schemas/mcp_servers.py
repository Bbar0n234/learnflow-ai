from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

from app.api.schemas.common import Page


class MCPServerCreate(BaseModel):
    name: str = Field(max_length=100)
    transport: Literal["http", "sse"]
    url: HttpUrl
    api_key: str | None = None
    allowed_tools: list[str] = []


class MCPServerUpdate(BaseModel):
    name: str | None = Field(None, max_length=100)
    transport: Literal["http", "sse"] | None = None
    url: HttpUrl | None = None
    api_key: str | None = None  # "" = remove, non-empty = update, absent = keep
    allowed_tools: list[str] | None = None
    is_active: bool | None = None


class MCPServerResponse(BaseModel):
    id: UUID
    name: str
    transport: str
    url: str
    has_api_key: bool
    api_key_hint: str | None = None
    allowed_tools: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class InheritedMCPServer(BaseModel):
    id: UUID
    name: str
    transport: str
    url: str
    has_api_key: bool
    api_key_hint: str | None = None
    is_active: bool
    is_disabled: bool


class MCPServerListResponse(Page[MCPServerResponse]):
    inherited: list[InheritedMCPServer] = []


class ToggleInheritedRequest(BaseModel):
    disabled: bool


class ToggleInheritedResponse(BaseModel):
    disabled: bool


class TestConnectionResponse(BaseModel):
    success: bool
    tools: list[str] = []
    error: str | None = None
