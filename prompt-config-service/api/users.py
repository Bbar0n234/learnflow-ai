"""API endpoints for user settings operations."""

import uuid
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.placeholder import PlaceholderValueSchema
from schemas.user_settings import SetPlaceholderRequest
from services.placeholder_service import PlaceholderService
from services.user_service import UserService

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/{user_id}/placeholders", response_model=Dict[str, PlaceholderValueSchema])
async def get_user_placeholders(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get current user placeholder settings."""
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID must be a positive integer"
        )
    
    service = UserService(db)
    
    try:
        settings = await service.get_user_settings(user_id)
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user settings: {str(e)}"
        )


@router.put("/{user_id}/placeholders/{placeholder_id}")
async def set_user_placeholder(
    user_id: int,
    placeholder_id: uuid.UUID,
    request: SetPlaceholderRequest,
    db: AsyncSession = Depends(get_db)
):
    """Set user placeholder value."""
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID must be a positive integer"
        )
    
    user_service = UserService(db)
    placeholder_service = PlaceholderService(db)
    
    # Verify placeholder exists
    placeholder = await placeholder_service.get_placeholder_by_id(placeholder_id)
    if not placeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placeholder {placeholder_id} not found"
        )
    
    # Verify value exists and belongs to this placeholder
    value = await placeholder_service.repo.find_value_by_id(request.value_id)
    if not value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placeholder value {request.value_id} not found"
        )
    
    if value.placeholder_id != placeholder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Value {request.value_id} does not belong to placeholder {placeholder_id}"
        )
    
    try:
        setting = await user_service.set_user_placeholder(
            user_id, placeholder_id, request.value_id
        )
        await db.commit()
        return {"message": "Placeholder value updated successfully"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update placeholder: {str(e)}"
        )


@router.post("/{user_id}/apply-profile/{profile_id}")
async def apply_profile_to_user(
    user_id: int,
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Apply profile settings to user."""
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID must be a positive integer"
        )
    
    service = UserService(db)
    
    try:
        await service.apply_profile_to_user(user_id, profile_id)
        await db.commit()
        return {"message": f"Profile {profile_id} applied to user {user_id} successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to apply profile: {str(e)}"
        )


@router.post("/{user_id}/reset")
async def reset_user_settings(
    user_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Reset user settings to defaults."""
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID must be a positive integer"
        )
    
    service = UserService(db)
    
    try:
        await service.reset_to_defaults(user_id)
        await db.commit()
        return {"message": f"User {user_id} settings reset to defaults"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset user settings: {str(e)}"
        )