"""Schemas for placeholder operations."""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PlaceholderValueSchema(BaseModel):
    """Schema for placeholder value."""
    
    id: uuid.UUID
    value: str
    display_name: str
    description: Optional[str] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}


class PlaceholderValueCreateSchema(BaseModel):
    """Schema for creating placeholder value."""
    
    placeholder_id: uuid.UUID
    value: str
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class PlaceholderSchema(BaseModel):
    """Schema for placeholder."""
    
    id: uuid.UUID
    name: str
    display_name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    values: List[PlaceholderValueSchema] = []
    
    model_config = {"from_attributes": True}


class PlaceholderCreateSchema(BaseModel):
    """Schema for creating placeholder."""
    
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None