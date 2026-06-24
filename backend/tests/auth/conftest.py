"""Local fixtures for the auth scope.

The shared ``app``/``client`` fixtures (backend/tests/conftest.py) override the
current-user provider — they ride *behind* auth and are wrong for testing auth
itself. Here ``get_current_user`` is left intact so tokens are minted and
validated for real (``/auth/login`` -> token -> walk with it). Lifespan does not
run under ASGITransport, so ``app.state.settings`` / ``rate_limiter`` (read by
the auth routes) are wired explicitly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from app.api.deps import get_db_session
from app.config import Settings
from app.infra.rate_limit import RateLimiter
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def settings() -> Settings:
    """Settings as the app sees them (JWT_SECRET defaulted in root conftest).

    The same instance is wired into ``app.state``, so tokens minted in a test
    with ``settings.jwt_secret`` verify against the running app.
    """
    return Settings()


@pytest.fixture
def auth_app(db_session: AsyncSession, settings: Settings) -> Iterator[FastAPI]:
    """A real-auth app: DB session overridden, current-user provider untouched."""
    # lazy: create_app builds Settings() at import; JWT_SECRET default (root
    # conftest) must be set first.
    from app.main import create_app  # noqa: PLC0415

    application = create_app()
    application.state.settings = settings
    application.state.rate_limiter = RateLimiter()

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _override_session
    yield application


@pytest_asyncio.fixture
async def auth_client(auth_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Unauthenticated async ASGI client over the real-auth app."""
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
