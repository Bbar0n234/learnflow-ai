"""API endpoints for profile operations."""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.profile import ProfileCreateSchema, ProfileSchema
from services.profile_service import ProfileService

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])


@router.get("/", response_model=List[ProfileSchema])
async def get_profiles(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get all profiles, optionally filtered by category."""
    service = ProfileService(db)
    profiles = await service.get_all_profiles(category=category)
    return profiles


@router.get("/{profile_id}", response_model=ProfileSchema)
async def get_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get profile by ID."""
    service = ProfileService(db)
    profile = await service.get_profile_by_id(profile_id)
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile {profile_id} not found"
        )
    
    return profile


@router.post("/", response_model=ProfileSchema, status_code=status.HTTP_201_CREATED)
async def create_profile(
    profile_data: ProfileCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new profile."""
    service = ProfileService(db)
    
    # Check if profile with same name already exists
    existing = await service.get_profile_by_name(profile_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profile with name '{profile_data.name}' already exists"
        )
    
    profile = await service.create_profile(profile_data)
    await db.commit()
    return profile