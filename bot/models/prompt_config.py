"""Pydantic models for prompt configuration data"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class PlaceholderValue(BaseModel):
    """Single value option for a placeholder"""
    
    id: str = Field(..., description="Unique identifier of the value")
    value: str = Field(..., description="Actual value for the placeholder")
    display_name: str = Field(..., description="User-friendly display name")
    description: Optional[str] = Field(None, description="Optional description")


class Placeholder(BaseModel):
    """Placeholder definition with available values"""
    
    id: str = Field(..., description="Unique identifier of the placeholder")
    name: str = Field(..., description="Technical name (e.g., role_perspective)")
    display_name: str = Field(..., description="User-friendly display name")
    description: Optional[str] = Field(None, description="Optional description")
    values: List[PlaceholderValue] = Field(default_factory=list, description="Available values")


class Profile(BaseModel):
    """Preset configuration profile"""
    
    id: str = Field(..., description="Unique identifier of the profile")
    name: str = Field(..., description="Profile name (e.g., technical_expert)")
    display_name: str = Field(..., description="User-friendly display name")
    description: Optional[str] = Field(None, description="Optional description")
    category: Optional[str] = Field(None, description="Profile category (style/subject)")


class UserPlaceholderSetting(BaseModel):
    """User's setting for a specific placeholder"""
    
    placeholder_id: str = Field(..., description="ID of the placeholder")
    placeholder_name: str = Field(..., description="Name of the placeholder")
    placeholder_display_name: str = Field(..., description="Display name of placeholder")
    value_id: str = Field(..., description="ID of selected value")
    value: str = Field(..., description="Actual value")
    display_name: str = Field(..., description="Display name of value")


class UserSettings(BaseModel):
    """Complete user prompt configuration settings"""
    
    user_id: int = Field(..., description="User ID")
    placeholders: Dict[str, UserPlaceholderSetting] = Field(
        default_factory=dict,
        description="Map of placeholder name to setting"
    )
    active_profile_id: Optional[str] = Field(None, description="Currently active profile ID")
    active_profile_name: Optional[str] = Field(None, description="Currently active profile name")


class ProfileWithSettings(Profile):
    """Profile with its placeholder settings"""
    
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Profile's placeholder settings"
    )


class GeneratePromptRequest(BaseModel):
    """Request to generate a prompt"""
    
    user_id: int = Field(..., description="User ID")
    node_name: str = Field(..., description="Node name for prompt generation")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Context variables for prompt"
    )


class GeneratePromptResponse(BaseModel):
    """Response with generated prompt"""
    
    prompt: str = Field(..., description="Generated prompt text")
    node_name: str = Field(..., description="Node name used")
    placeholders_used: List[str] = Field(
        default_factory=list,
        description="List of placeholder names used"
    )