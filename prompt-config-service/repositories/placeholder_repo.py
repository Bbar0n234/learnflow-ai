"""Repository for placeholder and placeholder value operations."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.placeholder import Placeholder, PlaceholderValue


class PlaceholderRepository:
    """Repository for managing placeholders and their values."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def find_by_id(self, placeholder_id: uuid.UUID) -> Optional[Placeholder]:
        """Find placeholder by ID."""
        result = await self.db.execute(
            select(Placeholder)
            .options(selectinload(Placeholder.values))
            .where(Placeholder.id == placeholder_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_name(self, name: str) -> Optional[Placeholder]:
        """Find placeholder by name."""
        result = await self.db.execute(
            select(Placeholder)
            .options(selectinload(Placeholder.values))
            .where(Placeholder.name == name)
        )
        return result.scalar_one_or_none()
    
    async def find_all(self, filters: Optional[Dict] = None) -> List[Placeholder]:
        """Find all placeholders with optional filters."""
        query = select(Placeholder).options(selectinload(Placeholder.values))
        
        if filters:
            # Add filtering logic if needed
            pass
            
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def create(self, data: Dict) -> Placeholder:
        """Create a new placeholder."""
        placeholder = Placeholder(**data)
        self.db.add(placeholder)
        await self.db.flush()
        await self.db.refresh(placeholder)
        return placeholder
    
    async def update(self, placeholder_id: uuid.UUID, data: Dict) -> Optional[Placeholder]:
        """Update placeholder by ID."""
        placeholder = await self.find_by_id(placeholder_id)
        if not placeholder:
            return None
            
        for key, value in data.items():
            if hasattr(placeholder, key):
                setattr(placeholder, key, value)
        
        await self.db.flush()
        await self.db.refresh(placeholder)
        return placeholder
    
    async def get_values(self, placeholder_id: uuid.UUID) -> List[PlaceholderValue]:
        """Get all values for a placeholder."""
        result = await self.db.execute(
            select(PlaceholderValue)
            .where(PlaceholderValue.placeholder_id == placeholder_id)
        )
        return list(result.scalars().all())
    
    async def create_value(self, data: Dict) -> PlaceholderValue:
        """Create a new placeholder value."""
        value = PlaceholderValue(**data)
        self.db.add(value)
        await self.db.flush()
        await self.db.refresh(value)
        return value
    
    async def find_value_by_id(self, value_id: uuid.UUID) -> Optional[PlaceholderValue]:
        """Find placeholder value by ID."""
        result = await self.db.execute(
            select(PlaceholderValue).where(PlaceholderValue.id == value_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_names(self, names: List[str]) -> List[Placeholder]:
        """Find multiple placeholders by their names."""
        result = await self.db.execute(
            select(Placeholder)
            .options(selectinload(Placeholder.values))
            .where(Placeholder.name.in_(names))
        )
        return list(result.scalars().all())