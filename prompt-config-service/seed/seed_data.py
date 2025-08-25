"""Script to seed the database with initial data."""

import asyncio
import json
import logging
import os
import sys
from typing import Dict, Any

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Add parent directory to path to import our modules  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings
from database import Base
from services.placeholder_service import PlaceholderService
from services.profile_service import ProfileService
from schemas.placeholder import PlaceholderCreateSchema, PlaceholderValueCreateSchema
from schemas.profile import ProfileCreateSchema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def load_seed_data() -> Dict[str, Any]:
    """Load seed data from JSON file."""
    data_path = settings.initial_data_path
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Seed data file not found: {data_path}")
    
    with open(data_path, "r", encoding="utf-8") as file:
        return json.load(file)


async def create_placeholders(db: AsyncSession, placeholders_data: list) -> Dict[str, str]:
    """Create placeholders and their values. Returns mapping of placeholder names to default value IDs."""
    service = PlaceholderService(db)
    placeholder_name_to_default_value_id = {}
    
    for ph_data in placeholders_data:
        logger.info(f"Creating placeholder: {ph_data['name']}")
        
        # Check if placeholder already exists
        existing = await service.get_placeholder_by_name(ph_data["name"])
        if existing:
            logger.info(f"Placeholder {ph_data['name']} already exists, skipping")
            continue
        
        # Create placeholder
        placeholder_schema = PlaceholderCreateSchema(
            name=ph_data["name"],
            display_name=ph_data["display_name"],
            description=ph_data.get("description")
        )
        placeholder = await service.create_placeholder(placeholder_schema)
        
        # Create values for this placeholder
        for value_data in ph_data["values"]:
            value_schema = PlaceholderValueCreateSchema(
                placeholder_id=placeholder.id,
                value=value_data["value"],
                display_name=value_data["display_name"],
                description=value_data.get("description")
            )
            value = await service.create_placeholder_value(value_schema)
            logger.info(f"Created value: {value_data['display_name']}")
    
    await db.commit()
    return placeholder_name_to_default_value_id


async def create_profiles(db: AsyncSession, profiles_data: list):
    """Create profiles and their settings."""
    profile_service = ProfileService(db)
    placeholder_service = PlaceholderService(db)
    
    for profile_data in profiles_data:
        logger.info(f"Creating profile: {profile_data['name']}")
        
        # Check if profile already exists
        existing = await profile_service.get_profile_by_name(profile_data["name"])
        if existing:
            logger.info(f"Profile {profile_data['name']} already exists, skipping")
            continue
        
        # Create profile
        profile_schema = ProfileCreateSchema(
            name=profile_data["name"],
            display_name=profile_data["display_name"],
            category=profile_data["category"],
            description=profile_data.get("description")
        )
        profile = await profile_service.create_profile(profile_schema)
        
        # Create profile settings
        for placeholder_name, value_text in profile_data["settings"].items():
            # Find placeholder
            placeholder = await placeholder_service.get_placeholder_by_name(placeholder_name)
            if not placeholder:
                logger.warning(f"Placeholder {placeholder_name} not found for profile {profile_data['name']}")
                continue
            
            # Find value
            placeholder_value = None
            for value in placeholder.values:
                if value.value == value_text:
                    placeholder_value = value
                    break
            
            if not placeholder_value:
                logger.warning(
                    f"Value '{value_text}' not found for placeholder {placeholder_name} "
                    f"in profile {profile_data['name']}"
                )
                continue
            
            # Create profile setting
            await profile_service.create_profile_setting(
                profile.id, placeholder.id, placeholder_value.id
            )
        
        logger.info(f"Created profile: {profile_data['display_name']}")
    
    await db.commit()


async def update_default_values_constant(db: AsyncSession, default_values: Dict[str, str]):
    """Generate DEFAULT_PLACEHOLDER_VALUES constant mapping."""
    placeholder_service = PlaceholderService(db)
    
    mapping = {}
    logger.info("Generating default values mapping:")
    
    for placeholder_name, default_value in default_values.items():
        placeholder = await placeholder_service.get_placeholder_by_name(placeholder_name)
        if not placeholder:
            logger.warning(f"Placeholder {placeholder_name} not found")
            continue
        
        # Find the value
        value_id = None
        for value in placeholder.values:
            if value.value == default_value:
                value_id = str(value.id)
                break
        
        if value_id:
            mapping[placeholder_name] = default_value
            logger.info(f"  {placeholder_name}: {default_value}")
        else:
            logger.warning(f"Default value '{default_value}' not found for {placeholder_name}")
    
    return mapping


async def seed_database():
    """Main function to seed the database."""
    logger.info("Starting database seeding...")
    
    # Create async engine
    database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
    
    # Remove sslmode parameter from URL as asyncpg handles SSL differently
    if "?sslmode=" in database_url:
        database_url = database_url.split("?sslmode=")[0]
    
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"ssl": None}  # Disable SSL for asyncpg
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")
    
    # Load seed data
    try:
        data = await load_seed_data()
        logger.info("Seed data loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load seed data: {e}")
        return
    
    # Seed data
    async with AsyncSession(engine) as session:
        try:
            # Create placeholders
            await create_placeholders(session, data["placeholders"])
            
            # Create profiles  
            await create_profiles(session, data["profiles"])
            
            # Update default values
            mapping = await update_default_values_constant(session, data["default_values"])
            
            logger.info("Database seeding completed successfully!")
            logger.info(f"DEFAULT_PLACEHOLDER_VALUES mapping: {mapping}")
            
        except Exception as e:
            logger.error(f"Failed to seed database: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_database())