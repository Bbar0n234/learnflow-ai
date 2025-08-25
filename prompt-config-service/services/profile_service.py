"""Service for profile operations."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.profile import Profile, ProfilePlaceholderSetting
from repositories.profile_repo import ProfileRepository
from schemas.profile import ProfileCreateSchema


class ProfileService:
    """Service for managing profiles."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProfileRepository(db)
    
    async def get_all_profiles(self, category: Optional[str] = None) -> List[Profile]:
        """Get all profiles, optionally filtered by category."""
        filters = {"category": category} if category else None
        return await self.repo.find_all(filters)
    
    async def get_profile_by_id(self, profile_id: uuid.UUID) -> Optional[Profile]:
        """Get profile by ID."""
        return await self.repo.find_by_id(profile_id)
    
    async def get_profile_by_name(self, name: str) -> Optional[Profile]:
        """Get profile by name."""
        return await self.repo.find_by_name(name)
    
    async def get_profile_settings(self, profile_id: uuid.UUID) -> Dict[str, str]:
        """Get profile settings as a dictionary of placeholder names to values."""
        settings = await self.repo.get_settings(profile_id)
        
        result = {}
        for setting in settings:
            if setting.placeholder and setting.placeholder_value:
                result[setting.placeholder.name] = setting.placeholder_value.value
        
        return result
    
    async def create_profile(self, data: ProfileCreateSchema) -> Profile:
        """Create a new profile."""
        return await self.repo.create(data.model_dump())
    
    async def update_profile_settings(self, profile_id: uuid.UUID, settings: Dict[str, uuid.UUID]) -> None:
        """Update profile settings."""
        # Convert settings dict to list format expected by repository
        settings_list = []
        for placeholder_name, value_id in settings.items():
            # We'll need to resolve placeholder_id from name in the repository
            # For now, assume we have the IDs
            settings_list.append({
                "placeholder_id": placeholder_name,  # This should be resolved to UUID
                "placeholder_value_id": value_id
            })
        
        await self.repo.update_settings(profile_id, settings_list)
    
    async def create_profile_setting(
        self, 
        profile_id: uuid.UUID, 
        placeholder_id: uuid.UUID, 
        value_id: uuid.UUID
    ) -> ProfilePlaceholderSetting:
        """Create a profile placeholder setting."""
        data = {
            "profile_id": profile_id,
            "placeholder_id": placeholder_id,
            "placeholder_value_id": value_id
        }
        return await self.repo.create_setting(data)