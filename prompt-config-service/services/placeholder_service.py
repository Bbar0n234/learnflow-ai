"""Service for placeholder operations."""

import uuid
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.placeholder import Placeholder, PlaceholderValue
from repositories.placeholder_repo import PlaceholderRepository
from schemas.placeholder import PlaceholderCreateSchema, PlaceholderValueCreateSchema


class PlaceholderService:
    """Service for managing placeholders."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PlaceholderRepository(db)
    
    async def get_all_placeholders(self) -> List[Placeholder]:
        """Get all placeholders with their values."""
        return await self.repo.find_all()
    
    async def get_placeholder_by_id(self, placeholder_id: uuid.UUID) -> Optional[Placeholder]:
        """Get placeholder by ID."""
        return await self.repo.find_by_id(placeholder_id)
    
    async def get_placeholder_by_name(self, name: str) -> Optional[Placeholder]:
        """Get placeholder by name."""
        return await self.repo.find_by_name(name)
    
    async def get_placeholder_values(self, placeholder_id: uuid.UUID) -> List[PlaceholderValue]:
        """Get all values for a placeholder."""
        return await self.repo.get_values(placeholder_id)
    
    async def create_placeholder(self, data: PlaceholderCreateSchema) -> Placeholder:
        """Create a new placeholder."""
        return await self.repo.create(data.model_dump())
    
    async def create_placeholder_value(self, data: PlaceholderValueCreateSchema) -> PlaceholderValue:
        """Create a new placeholder value."""
        return await self.repo.create_value(data.model_dump())
    
    async def update_placeholder_value(
        self, value_id: uuid.UUID, data: Dict
    ) -> Optional[PlaceholderValue]:
        """Update placeholder value."""
        value = await self.repo.find_value_by_id(value_id)
        if not value:
            return None
            
        for key, val in data.items():
            if hasattr(value, key):
                setattr(value, key, val)
        
        await self.db.flush()
        await self.db.refresh(value)
        return value
    
    async def get_placeholders_by_names(self, names: List[str]) -> List[Placeholder]:
        """Get multiple placeholders by their names."""
        return await self.repo.find_by_names(names)