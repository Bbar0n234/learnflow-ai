"""Database engine/session factories and the request-scoped session dependency."""

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from siem_service.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine (owned by lifespan, stored in app.state)."""
    # asyncpg driver: statement_timeout via server_settings (milliseconds as str).
    # Does NOT introduce idle_in_transaction_session_timeout — per-statement only.
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "statement_timeout": str(settings.db_statement_timeout_seconds * 1000)
            }
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory bound to the given engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped session from the lifespan-owned factory."""
    session_factory: async_sessionmaker[AsyncSession] = (
        request.app.state.session_factory
    )
    async with session_factory() as session:
        yield session
