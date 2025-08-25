"""API endpoints for placeholder operations."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.placeholder import (
    PlaceholderCreateSchema,
    PlaceholderSchema,
    PlaceholderValueCreateSchema,
    PlaceholderValueSchema,
)
from services.placeholder_service import PlaceholderService

router = APIRouter(prefix="/api/v1/placeholders", tags=["placeholders"])


@router.get("/", response_model=List[PlaceholderSchema])
async def get_placeholders(db: AsyncSession = Depends(get_db)):
    """Get all placeholders with their values."""
    service = PlaceholderService(db)
    placeholders = await service.get_all_placeholders()
    return placeholders


@router.get("/{placeholder_id}", response_model=PlaceholderSchema)
async def get_placeholder(
    placeholder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get placeholder by ID."""
    service = PlaceholderService(db)
    placeholder = await service.get_placeholder_by_id(placeholder_id)
    
    if not placeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placeholder {placeholder_id} not found"
        )
    
    return placeholder


@router.get("/{placeholder_id}/values", response_model=List[PlaceholderValueSchema])
async def get_placeholder_values(
    placeholder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get all values for a placeholder."""
    service = PlaceholderService(db)
    
    # Verify placeholder exists
    placeholder = await service.get_placeholder_by_id(placeholder_id)
    if not placeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placeholder {placeholder_id} not found"
        )
    
    values = await service.get_placeholder_values(placeholder_id)
    return values


@router.post("/", response_model=PlaceholderSchema, status_code=status.HTTP_201_CREATED)
async def create_placeholder(
    placeholder_data: PlaceholderCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new placeholder."""
    service = PlaceholderService(db)
    
    # Check if placeholder with same name already exists
    existing = await service.get_placeholder_by_name(placeholder_data.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Placeholder with name '{placeholder_data.name}' already exists"
        )
    
    placeholder = await service.create_placeholder(placeholder_data)
    await db.commit()
    return placeholder


@router.post(
    "/{placeholder_id}/values",
    response_model=PlaceholderValueSchema,
    status_code=status.HTTP_201_CREATED
)
async def create_placeholder_value(
    placeholder_id: uuid.UUID,
    value_data: PlaceholderValueCreateSchema,
    db: AsyncSession = Depends(get_db)
):
    """Create a new value for a placeholder."""
    service = PlaceholderService(db)
    
    # Verify placeholder exists
    placeholder = await service.get_placeholder_by_id(placeholder_id)
    if not placeholder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Placeholder {placeholder_id} not found"
        )
    
    # Set the placeholder_id in the data
    value_data.placeholder_id = placeholder_id
    
    value = await service.create_placeholder_value(value_data)
    await db.commit()
    return value