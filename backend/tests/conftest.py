"""Backend test fixtures: real-Postgres DB harness + authenticated ASGI client.

Builds on the cross-project ``postgres_container`` fixture (learnflow_testing
plugin). Schema comes from ``alembic upgrade head``; each test runs inside a
transaction rolled back in teardown. The default HTTP client is authenticated by
overriding the current-user provider (no real JWT) — for tests of functionality
*behind* auth, not the auth flow itself.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from app.api.deps import get_current_user, get_db_session
from app.models.user import User
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from learnflow_testing.db import (
    DbUrls,
    create_database,
    make_urls,
    run_migrations,
    transactional_session,
    worker_db_name,
)
from learnflow_testing.factories import UserFactory, bind_session
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Settings() requires JWT_SECRET; default it before any fixture builds the app or
# runs migrations. Placed after imports so the import block stays at the top.
os.environ.setdefault("JWT_SECRET", "test-secret")

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = str(_BACKEND_ROOT / "alembic.ini")
_DB_NAME = worker_db_name("learnflow_test")


@pytest.fixture(scope="session")
def db_urls(postgres_container: object) -> DbUrls:
    """Per-worker backend DB URL (psycopg async driver) on the shared container."""
    container_url = postgres_container.get_connection_url()  # type: ignore[attr-defined]
    return make_urls(container_url, _DB_NAME, driver="psycopg")


@pytest.fixture(scope="session")
def _migrated_db(db_urls: DbUrls) -> DbUrls:
    """Create the per-worker DB and bring it to head once per session."""
    asyncio.run(create_database(db_urls.admin_url, _DB_NAME))
    run_migrations(
        _ALEMBIC_INI,
        db_urls.db_url,
        {"DATABASE_URL": db_urls.db_url, "JWT_SECRET": "test-secret"},
    )
    return db_urls


@pytest.fixture(scope="session")
def engine(_migrated_db: DbUrls) -> Iterator[AsyncEngine]:
    """Session-scoped engine with NullPool.

    NullPool means each ``connect()`` opens a fresh connection in the caller's
    event loop — so a session-scoped engine stays compatible with function-scoped
    test loops without cross-loop connection reuse.
    """
    eng = create_async_engine(_migrated_db.db_url, poolclass=NullPool)
    yield eng
    asyncio.run(eng.dispose())


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Function-scoped transactional session; rolled back after the test.

    Factories are bound to this session, so ``await UserFactory.create()``
    persists into the same transaction the code under test reads.
    """
    async with transactional_session(engine) as session:
        bind_session(session)
        yield session


@pytest_asyncio.fixture
async def current_user(db_session: AsyncSession) -> User:
    """A persisted user the authenticated client acts as."""
    user: User = await UserFactory.create()
    return user


@pytest.fixture
def app(db_session: AsyncSession, current_user: User) -> FastAPI:
    """A fresh app with the DB session and current-user provider overridden.

    Lifespan does not run under ASGITransport, so app.state is never populated;
    we override the providers that would have read it.

    LIMITATION — single shared session: the handler is given the *same*
    ``db_session`` the test body and factories use, so the client sees fixture
    data without committing. The cost is that this one ``AsyncSession`` cannot
    run two operations at once: **concurrent requests in a single test**
    (``asyncio.gather(client.get(...), client.get(...))``, or an open SSE stream
    plus a second call) raise ``InterfaceError: another operation is in
    progress``. This is fundamental to transactional-rollback isolation (one
    connection per test), not a harness bug — see ``transactional_session`` in
    ``learnflow_testing.db``. Tests needing concurrency must serialize their
    requests, or commit data and clean up with ``TRUNCATE`` instead of relying
    on the shared transaction (narrow).
    """
    # lazy: app.main builds Settings() at import (module-level create_app); the
    # JWT_SECRET default above must be set first.
    from app.main import create_app  # noqa: PLC0415

    application = create_app()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _override_user() -> User:
        return current_user

    application.dependency_overrides[get_db_session] = _override_session
    application.dependency_overrides[get_current_user] = _override_user
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Authenticated async ASGI client (in-memory, no socket).

    Shares one transactional ``db_session`` with the test body (see ``app``):
    concurrent requests in a single test are unsupported — issue them serially.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
