"""Repository for user settings operations."""

import uuid
from typing import Dict, List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.placeholder import Placeholder, PlaceholderValue
from models.user_settings import UserPlaceholderSetting, UserProfile


class UserSettingsRepository:
    """Repository for managing user settings."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_user_profile(self, user_id: int) -> UserProfile:
        """Get or create user profile."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        user_profile = result.scalar_one_or_none()
        
        if not user_profile:
            user_profile = UserProfile(user_id=user_id)
            self.db.add(user_profile)
            await self.db.flush()
            await self.db.refresh(user_profile)
        
        return user_profile
    
    async def get_user_settings(self, user_id: int) -> List[UserPlaceholderSetting]:
        """Get all placeholder settings for a user."""
        result = await self.db.execute(
            select(UserPlaceholderSetting)
            .options(
                selectinload(UserPlaceholderSetting.placeholder),
                selectinload(UserPlaceholderSetting.placeholder_value)
            )
            .where(UserPlaceholderSetting.user_id == user_id)
        )
        return list(result.scalars().all())
    
    async def get_user_settings_by_names(
        self, user_id: int, placeholder_names: List[str]
    ) -> Dict[str, str]:
        """
        Get placeholder values by their names for a specific user.
        Returns a dictionary {placeholder_name: value}.
        """
        result = await self.db.execute(
            select(
                Placeholder.name,
                PlaceholderValue.value
            )
            .join(UserPlaceholderSetting, UserPlaceholderSetting.placeholder_id == Placeholder.id)
            .join(PlaceholderValue, UserPlaceholderSetting.placeholder_value_id == PlaceholderValue.id)
            .where(
                UserPlaceholderSetting.user_id == user_id,
                Placeholder.name.in_(placeholder_names)
            )
        )
        
        return {name: value for name, value in result.all()}
    
    async def upsert_setting(
        self, user_id: int, placeholder_id: uuid.UUID, value_id: uuid.UUID
    ) -> UserPlaceholderSetting:
        """Create or update a user placeholder setting."""
        # Check if setting already exists
        result = await self.db.execute(
            select(UserPlaceholderSetting)
            .where(
                UserPlaceholderSetting.user_id == user_id,
                UserPlaceholderSetting.placeholder_id == placeholder_id
            )
        )
        setting = result.scalar_one_or_none()
        
        if setting:
            # Update existing setting
            setting.placeholder_value_id = value_id
        else:
            # Create new setting
            setting = UserPlaceholderSetting(
                user_id=user_id,
                placeholder_id=placeholder_id,
                placeholder_value_id=value_id
            )
            self.db.add(setting)
        
        await self.db.flush()
        await self.db.refresh(setting)
        return setting
    
    async def delete_user_settings(self, user_id: int) -> None:
        """Delete all settings for a user."""
        await self.db.execute(
            delete(UserPlaceholderSetting)
            .where(UserPlaceholderSetting.user_id == user_id)
        )
        await self.db.flush()
    
    async def bulk_upsert(self, user_id: int, settings: List[Dict]) -> None:
        """Bulk create or update user settings."""
        for setting_data in settings:
            await self.upsert_setting(
                user_id=user_id,
                placeholder_id=setting_data["placeholder_id"],
                value_id=setting_data["placeholder_value_id"]
            )
    
    async def ensure_user_exists(self, user_id: int) -> UserProfile:
        """Ensure user profile exists, create if not."""
        return await self.get_user_profile(user_id)