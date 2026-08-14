"""Fixtures for the OAuth scope.

The stand is wired like ``tests/auth``: lifespan does not run under
``ASGITransport``, so everything the OAuth routes read off ``app.state`` is
placed there explicitly — the provider registry, the geoip reader, the rate
limiter and settings. The DB session is the shared transactional one, so the
callback's find-or-create writes into real PostgreSQL and rolls back.

``Settings`` is always built with explicit keyword arguments: ``make
test-scope`` sources ``.env``/``.env.local`` into the environment, and
``BaseSettings`` would otherwise let a developer's local creds, geo fallback
or cookie flags decide what these tests assert.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Protocol

import pytest_asyncio
from app.api.deps import get_db_session
from app.config import Settings
from app.infra.rate_limit import RateLimiter
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.oauth._helpers import (
    JWT_SECRET,
    REDIRECT_BASE_URL,
    FakeProvider,
    all_fake_providers,
)


def build_settings(**overrides: Any) -> Settings:
    """Deterministic settings; ``overrides`` name the knob a test cares about."""
    defaults: dict[str, Any] = {
        "jwt_secret": JWT_SECRET,
        "secure_cookies": False,
        "client_ip_source": "socket",
        "oauth_redirect_base_url": REDIRECT_BASE_URL,
        "geoip_db_path": "",
        "geoip_fallback_country": "RU",
    }
    return Settings(**{**defaults, **overrides})


@dataclass
class OAuthStand:
    """One wired application plus the handles a test asserts against."""

    app: FastAPI
    client: AsyncClient
    providers: dict[str, FakeProvider]
    settings: Settings

    @property
    def yandex(self) -> FakeProvider:
        return self.providers["yandex"]


class StandFactory(Protocol):
    async def __call__(
        self,
        *,
        providers: dict[str, FakeProvider] | None = ...,
        fallback_country: str = ...,
        geoip_reader: object | None = ...,
        secure_cookies: bool = ...,
        client_ip_source: str = ...,
    ) -> OAuthStand: ...


@pytest_asyncio.fixture
async def stand_factory(db_session: AsyncSession) -> AsyncIterator[StandFactory]:
    """Builds OAuth stands on demand; every client is closed on teardown.

    A factory rather than a plain fixture because the country, the active
    registry and the cookie-security flag vary per case, and each stand needs
    its own ``RateLimiter`` so budgets never leak between tests.

    ``client_ip_source`` exists for one reason: under ``ASGITransport`` every
    request comes from the same socket address, so a stand left on ``socket``
    cannot tell a per-IP budget from a global one. Switching it to
    ``x-real-ip`` makes the client's address something the test controls.
    """
    async with AsyncExitStack() as stack:

        async def _make(
            *,
            providers: dict[str, FakeProvider] | None = None,
            fallback_country: str = "RU",
            geoip_reader: object | None = None,
            secure_cookies: bool = False,
            client_ip_source: str = "socket",
        ) -> OAuthStand:
            # lazy: app.main builds Settings() at import; the root conftest
            # defaults JWT_SECRET before anything imports it.
            from app.main import create_app  # noqa: PLC0415

            registry = all_fake_providers() if providers is None else providers
            settings = build_settings(
                geoip_fallback_country=fallback_country,
                secure_cookies=secure_cookies,
                client_ip_source=client_ip_source,
            )

            application = create_app()
            application.state.settings = settings
            application.state.rate_limiter = RateLimiter()
            application.state.oauth_providers = registry
            application.state.geoip_reader = geoip_reader

            async def _override_session() -> AsyncIterator[AsyncSession]:
                yield db_session

            application.dependency_overrides[get_db_session] = _override_session

            client = await stack.enter_async_context(
                AsyncClient(
                    transport=ASGITransport(app=application),
                    base_url="http://test",
                )
            )
            return OAuthStand(
                app=application,
                client=client,
                providers=registry,
                settings=settings,
            )

        yield _make


@pytest_asyncio.fixture
async def stand(stand_factory: StandFactory) -> OAuthStand:
    """Default stand: all three providers active, geo fallback ``RU``."""
    return await stand_factory()
