"""API endpoints for profile operations."""

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.profile import ProfileCreateSchema, ProfileSchema
from services.profile_service import ProfileService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("/", response_model=List[ProfileSchema])
async def get_profiles(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all profiles, optionally filtered by category."""
    try:
        service = ProfileService(db)
        profiles = await service.get_all_profiles(category=category)
        logger.info(f"Retrieved {len(profiles)} profiles (category: {category or 'all'})")
        
        # Log first profile structure for debugging serialization issues
        if profiles:
            first_profile = profiles[0]
            logger.debug(f"Sample profile structure - ID: {first_profile.id}, Name: {first_profile.name}, Settings count: {len(first_profile.placeholder_settings)}")
        
        return profiles
    except Exception as e:
        logger.error(f"Failed to get profiles: {e}")
        raise


@router.get("/{profile_id}", response_model=ProfileSchema)
async def get_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get profile by ID."""
    try:
        service = ProfileService(db)
        profile = await service.get_profile_by_id(profile_id)
        
        if not profile:
            logger.warning(f"Profile not found: {profile_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Profile {profile_id} not found"
            )
        
        logger.info(f"Retrieved profile: {profile.name} ({profile_id})")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get profile {profile_id}: {e}")
        raise


@router.post("/", response_model=ProfileSchema, status_code=status.HTTP_201_CREATED)
async def create_profile(
    profile_data: ProfileCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new profile."""
    try:
        service = ProfileService(db)
        
        # Check if profile with same name already exists
        existing = await service.get_profile_by_name(profile_data.name)
        if existing:
            logger.warning(f"Attempted to create duplicate profile: {profile_data.name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Profile with name '{profile_data.name}' already exists"
            )
        
        profile = await service.create_profile(profile_data)
        await db.commit()
        logger.info(f"Created profile: {profile.name} ({profile.id})")
        return profile
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create profile {profile_data.name}: {e}")
        raise