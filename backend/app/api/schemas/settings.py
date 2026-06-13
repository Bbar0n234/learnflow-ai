from __future__ import annotations

from pydantic import BaseModel

from app.api.schemas.common import Page


class SettingsUpdate(BaseModel):
    model_name: str | None = None
    extra_body: dict | None = None


class SettingsResponse(BaseModel):
    model_name: str | None
    extra_body: dict | None
    resolved_model: str
    resolved_source: str


class AvailableModelResponse(BaseModel):
    name: str
    display_name: str


class ModelsListResponse(Page[AvailableModelResponse]):
    pass
