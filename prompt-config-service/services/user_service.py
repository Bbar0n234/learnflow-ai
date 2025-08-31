"""Service for user settings operations."""

import logging
import uuid
from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession

from models.placeholder import PlaceholderValue
from models.user_settings import UserPlaceholderSetting, UserProfile
from repositories.placeholder_repo import PlaceholderRepository

logger = logging.getLogger(__name__)
from repositories.user_settings_repo import UserSettingsRepository


# Default placeholder values - map placeholder name to value name from yaml
DEFAULT_PLACEHOLDER_VALUES = {
    "role_perspective": "simplification_expert",
    "subject_name": "ai_llm",
    "subject_keywords": "ai_llm_keywords",
    "language": "russian_tech",
    "style": "comprehensive_detailed",
    "target_audience_inline": "working_professionals",
    "target_audience_block": "working_professionals_block",
    "material_type_inline": "comprehensive_study",
    "material_type_block": "comprehensive_study_block",
    "explanation_depth": "balanced_coverage",
    "topic_coverage": "progressive_learning",
    "question_formats": "open_ended",
    "question_purpose": "verify_understanding_block",
    "question_purpose_inline": "verify_understanding",
    "question_quantity": "qty_3",
}


class UserService:
    """Service for managing user settings."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserSettingsRepository(db)
        self.placeholder_repo = PlaceholderRepository(db)
    
    async def get_user_settings(self, user_id: int) -> Dict[str, PlaceholderValue]:
        """Get user settings as a dictionary of placeholder names to PlaceholderValue objects."""
        await self.ensure_user_exists(user_id)
        settings = await self.repo.get_user_settings(user_id)
        
        result = {}
        for setting in settings:
            if setting.placeholder and setting.placeholder_value:
                result[setting.placeholder.name] = setting.placeholder_value
        
        return result
    
    async def get_user_settings_with_details(self, user_id: int):
        """Get user settings with full placeholder and value details."""
        await self.ensure_user_exists(user_id)
        return await self.repo.get_user_settings(user_id)
    
    async def get_user_placeholder_values(
        self, user_id: int, placeholder_names: List[str]
    ) -> Dict[str, str]:
        """Get placeholder values for specific placeholder names."""
        await self.ensure_user_exists(user_id)
        return await self.repo.get_user_settings_by_names(user_id, placeholder_names)
    
    async def set_user_placeholder(
        self, user_id: int, placeholder_id: uuid.UUID, value_id: uuid.UUID
    ) -> UserPlaceholderSetting:
        """Set a user placeholder value."""
        await self.ensure_user_exists(user_id)
        return await self.repo.upsert_setting(user_id, placeholder_id, value_id)
    
    async def apply_profile_to_user(self, user_id: int, profile_id: uuid.UUID) -> None:
        """Apply a profile's settings to a user."""
        from services.profile_service import ProfileService
        
        await self.ensure_user_exists(user_id)
        
        profile_service = ProfileService(self.db)
        profile = await profile_service.get_profile_by_id(profile_id)
        
        if not profile:
            raise ValueError(f"Profile {profile_id} not found")
        
        # Get profile settings and apply them to user
        settings_list = []
        for setting in profile.placeholder_settings:
            settings_list.append({
                "placeholder_id": setting.placeholder_id,
                "placeholder_value_id": setting.placeholder_value_id
            })
        
        if settings_list:
            await self.repo.bulk_upsert(user_id, settings_list)
    
    async def reset_to_defaults(self, user_id: int) -> None:
        """Reset user settings to defaults."""
        await self.ensure_user_exists(user_id)
        await self.apply_default_settings(user_id)
    
    async def ensure_user_exists(self, user_id: int) -> UserProfile:
        """Ensure user exists, create with default settings if not."""
        user_profile = await self.repo.ensure_user_exists(user_id)
        
        # Check if user has any settings
        settings = await self.repo.get_user_settings(user_id)
        if not settings:
            # Apply default settings for new user
            await self.apply_default_settings(user_id)
        
        return user_profile
    
    async def apply_default_settings(self, user_id: int) -> None:
        """Apply default settings to user."""
        # Delete existing settings
        await self.repo.delete_user_settings(user_id)
        logger.info(f"Deleted existing settings for user {user_id}")
        
        # Apply default values
        settings_to_create = []
        
        for placeholder_name, default_value_name in DEFAULT_PLACEHOLDER_VALUES.items():
            # Find placeholder by name
            placeholder = await self.placeholder_repo.find_by_name(placeholder_name)
            if not placeholder:
                logger.warning(f"Placeholder '{placeholder_name}' not found in database")
                continue
                
            # Find value by name
            placeholder_value = None
            for value in placeholder.values:
                if value.name == default_value_name:
                    placeholder_value = value
                    break
            
            if placeholder_value:
                logger.debug(f"Found value '{default_value_name}' for placeholder '{placeholder_name}'")
                settings_to_create.append({
                    "placeholder_id": placeholder.id,
                    "placeholder_value_id": placeholder_value.id
                })
            else:
                logger.warning(f"Value '{default_value_name}' not found for placeholder '{placeholder_name}'. Available values: {[v.name for v in placeholder.values]}")
        
        logger.info(f"Prepared {len(settings_to_create)} settings for user {user_id}")
        if settings_to_create:
            await self.repo.bulk_upsert(user_id, settings_to_create)
            logger.info(f"Successfully inserted {len(settings_to_create)} settings for user {user_id}")
        else:
            logger.error(f"No settings to create for user {user_id}!")