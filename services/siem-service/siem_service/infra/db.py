"""Database setup and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from siem_service.config import Settings

_engine = None
_async_session_maker = None


async def init_db(settings: Settings) -> None:
    """Initialize database engine and session maker."""
    global _engine, _async_session_maker

    _engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    if _async_session_maker is None:
        raise RuntimeError("Database not initialized")

    async with _async_session_maker() as session:
        yield session


def get_async_session_maker() -> "async_sessionmaker[AsyncSession]":
    """Get async session maker (for non-lifespan use)."""
    if _async_session_maker is None:
        raise RuntimeError("Database not initialized")
    return _async_session_maker
