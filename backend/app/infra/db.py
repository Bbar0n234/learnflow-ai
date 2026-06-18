from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    # psycopg driver: statement_timeout via libpq options (milliseconds).
    # Does NOT introduce idle_in_transaction_session_timeout — per-statement only.
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        connect_args={
            "options": f"-c statement_timeout={settings.db_statement_timeout_seconds * 1000}"
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
