"""SIEM-service test fixtures: real-Postgres DB harness on the shared container.

Mirrors the backend harness but for the independent siem alembic chain (asyncpg
driver, ``SIEM_*`` env vars). Schema via ``alembic upgrade head``; per-test
transactional rollback.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from learnflow_testing.db import (
    DbUrls,
    create_database,
    make_urls,
    run_migrations,
    transactional_session,
    worker_db_name,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Settings() requires SIEM_JWT_SECRET; default it before any fixture builds the
# app or runs migrations.
os.environ.setdefault("SIEM_JWT_SECRET", "test-secret")

_SIEM_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = str(_SIEM_ROOT / "alembic.ini")
_DB_NAME = worker_db_name("siem_test")
_MIGRATION_ENV = {"SIEM_JWT_SECRET": "test-secret"}


@pytest.fixture(scope="session")
def db_urls(postgres_container: object) -> DbUrls:
    """Per-worker siem DB URL (asyncpg driver) on the shared container."""
    container_url = postgres_container.get_connection_url()  # type: ignore[attr-defined]
    return make_urls(container_url, _DB_NAME, driver="asyncpg")


@pytest.fixture(scope="session")
def _migrated_db(db_urls: DbUrls) -> DbUrls:
    asyncio.run(create_database(db_urls.admin_url, _DB_NAME))
    run_migrations(
        _ALEMBIC_INI,
        db_urls.db_url,
        {"SIEM_DATABASE_URL": db_urls.db_url, **_MIGRATION_ENV},
    )
    return db_urls


@pytest.fixture(scope="session")
def engine(_migrated_db: DbUrls) -> Iterator[AsyncEngine]:
    eng = create_async_engine(_migrated_db.db_url, poolclass=NullPool)
    yield eng
    asyncio.run(eng.dispose())


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with transactional_session(engine) as session:
        yield session
