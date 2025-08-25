"""Database configuration and connection management."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Create async engine
database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

# Remove sslmode parameter from URL as asyncpg handles SSL differently
if "?sslmode=" in database_url:
    database_url = database_url.split("?sslmode=")[0]

engine = create_async_engine(
    database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.log_level == "DEBUG",
    connect_args={"ssl": None}  # Disable SSL for asyncpg
)

# Create async session maker
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database by creating all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)