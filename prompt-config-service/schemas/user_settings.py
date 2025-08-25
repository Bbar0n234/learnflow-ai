"""Schemas for user settings operations."""

import uuid
from datetime import datetime
from typing import Dict, List

from pydantic import BaseModel

from schemas.placeholder import PlaceholderValueSchema


class UserPlaceholderSettingSchema(BaseModel):
    """Schema for user placeholder setting."""
    
    placeholder_id: uuid.UUID
    placeholder_value_id: uuid.UUID
    placeholder_name: str
    placeholder_display_name: str
    value: str
    value_display_name: str
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class UserSettingsSchema(BaseModel):
    """Schema for user settings."""
    
    user_id: int
    settings: List[UserPlaceholderSettingSchema]
    created_at: datetime
    updated_at: datetime


class SetPlaceholderRequest(BaseModel):
    """Schema for setting placeholder value."""
    
    value_id: uuid.UUID