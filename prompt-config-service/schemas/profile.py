"""Schemas for profile operations."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.placeholder import PlaceholderValueSchema


class ProfileSettingSchema(BaseModel):
    """Schema for profile placeholder setting."""
    
    placeholder_id: uuid.UUID
    placeholder_value_id: uuid.UUID
    placeholder_name: Optional[str] = None
    placeholder_value: Optional[PlaceholderValueSchema] = None
    
    model_config = {"from_attributes": True}


class ProfileSchema(BaseModel):
    """Schema for profile."""
    
    id: uuid.UUID
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    created_at: datetime
    updated_at: datetime
    placeholder_settings: List[ProfileSettingSchema] = []
    
    model_config = {"from_attributes": True}


class ProfileCreateSchema(BaseModel):
    """Schema for creating profile."""
    
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=50)


class ProfileUpdateSettingsSchema(BaseModel):
    """Schema for updating profile settings."""
    
    settings: Dict[str, uuid.UUID] = Field(
        ..., 
        description="Dictionary mapping placeholder names to value IDs"
    )