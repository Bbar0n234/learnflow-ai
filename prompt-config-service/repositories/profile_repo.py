"""Repository for profile operations."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.profile import Profile, ProfilePlaceholderSetting


class ProfileRepository:
    """Repository for managing profiles and their settings."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_id(self, profile_id: uuid.UUID) -> Optional[Profile]:
        """Find profile by ID."""
        result = await self.db.execute(
            select(Profile)
            .options(selectinload(Profile.placeholder_settings))
            .where(Profile.id == profile_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_name(self, name: str) -> Optional[Profile]:
        """Find profile by name."""
        result = await self.db.execute(
            select(Profile)
            .options(selectinload(Profile.placeholder_settings))
            .where(Profile.name == name)
        )
        return result.scalar_one_or_none()
    
    async def find_all(self, filters: Optional[Dict] = None) -> List[Profile]:
        """Find all profiles with optional filters."""
        query = select(Profile).options(selectinload(Profile.placeholder_settings))
        
        if filters and "category" in filters:
            query = query.where(Profile.category == filters["category"])
            
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create(self, data: Dict) -> Profile:
        """Create a new profile."""
        profile = Profile(**data)
        self.db.add(profile)
        await self.db.flush()
        await self.db.refresh(profile)
        return profile
    
    async def update(self, profile_id: uuid.UUID, data: Dict) -> Optional[Profile]:
        """Update profile by ID."""
        profile = await self.find_by_id(profile_id)
        if not profile:
            return None
            
        for key, value in data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        
        await self.db.flush()
        await self.db.refresh(profile)
        return profile
    
    async def get_settings(self, profile_id: uuid.UUID) -> List[ProfilePlaceholderSetting]:
        """Get all placeholder settings for a profile."""
        result = await self.db.execute(
            select(ProfilePlaceholderSetting)
            .options(
                selectinload(ProfilePlaceholderSetting.placeholder),
                selectinload(ProfilePlaceholderSetting.placeholder_value)
            )
            .where(ProfilePlaceholderSetting.profile_id == profile_id)
        )
        return list(result.scalars().all())
    
    async def update_settings(self, profile_id: uuid.UUID, settings: List[Dict]) -> None:
        """Update profile placeholder settings."""
        # Delete existing settings
        await self.db.execute(
            select(ProfilePlaceholderSetting)
            .where(ProfilePlaceholderSetting.profile_id == profile_id)
        )
        
        # Create new settings
        for setting_data in settings:
            setting = ProfilePlaceholderSetting(
                profile_id=profile_id,
                **setting_data
            )
            self.db.add(setting)
        
        await self.db.flush()
    
    async def create_setting(self, data: Dict) -> ProfilePlaceholderSetting:
        """Create a new profile placeholder setting."""
        setting = ProfilePlaceholderSetting(**data)
        self.db.add(setting)
        await self.db.flush()
        await self.db.refresh(setting)
        return setting