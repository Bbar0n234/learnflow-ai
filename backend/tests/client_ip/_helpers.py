"""Builders for the client-IP scope: requests, settings and a wired app.

Pure functions, not fixtures — imported by the modules of this scope.

Two seams are exercised and they take their configuration from different
places, mirroring production wiring:

* ``get_client_ip`` is a plain function: unit tests hand it a ``Request`` built
  from an ASGI scope plus an explicit ``Settings``.
* the app-level path reads the knobs from the **environment** — ``create_app``
  captures ``Settings()`` in the middleware closure, and lifespan publishes
  another instance as ``app.state.settings`` for the routes. Tests therefore
  set ``CLIENT_IP_SOURCE`` / ``CLIENT_IP_XFF_HOPS`` before building the app, so
  both consumers see the same values exactly as they do on a real boot.

Addresses come from the documentation ranges (RFC 5737) so that a value in an
assertion is never mistaken for a real host: ``198.51.100.x`` is the TCP peer,
``203.0.113.x`` is what a client puts into proxy headers itself, ``192.0.2.x``
is what the reverse proxy appends.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal

import pytest
import structlog
from app.api.deps import get_db_session
from app.config import Settings
from app.infra.rate_limit import RateLimiter
from app.main import create_app
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

IpSource = Literal["socket", "x-real-ip", "x-forwarded-for"]

SOCKET_IP = "198.51.100.10"
OTHER_SOCKET_IP = "198.51.100.99"
CLIENT_SPOOF_IP = "203.0.113.66"
PROXY_APPENDED_IP = "192.0.2.7"

#: Observation point mounted by :func:`build_app` — reports what the middleware
#: left in structlog contextvars for downstream code to log.
PROBE_PATH = "/api/_client_ip_probe"


def make_request(
    *,
    path: str = "/api/auth/login",
    headers: dict[str, str] | None = None,
    client: tuple[str, int] | None = (SOCKET_IP, 51234),
) -> Request:
    """A Starlette ``Request`` over a hand-built ASGI scope.

    ``client=None`` models a transport that reports no peer (the case the
    helper answers with ``"unknown"``).
    """
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "server": ("testserver", 80),
        "root_path": "",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in (headers or {}).items()
        ],
        "client": client,
    }
    return Request(scope)


def make_settings(source: IpSource = "socket", hops: int = 1) -> Settings:
    """Settings with the client-IP knobs pinned (the rest from the env)."""
    return Settings(client_ip_source=source, client_ip_xff_hops=hops)


class _UnavailableEngine:
    """Engine stand-in whose ``connect()`` fails the way a down DB does.

    Lets ``/health`` run its documented 503 branch (and emit its own log line)
    without a database — the health path is where we assert that no ``ip`` is
    bound.
    """

    def connect(self) -> Any:
        raise OperationalError("SELECT 1", {}, Exception("database unavailable"))


def _mount_probe(app: FastAPI) -> None:
    async def probe() -> dict[str, str]:
        return {
            key: str(value)
            for key, value in structlog.contextvars.get_contextvars().items()
        }

    app.add_api_route(PROBE_PATH, probe, methods=["GET"])
    # Route order matters: create_app appends a frontend catch-all when
    # frontend/dist exists, and it would answer /api/* with a 404. Moving the
    # probe to the front keeps this scope green whether or not the frontend was
    # built locally.
    app.router.routes.insert(0, app.router.routes.pop())


def build_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source: IpSource = "socket",
    hops: int = 1,
    session: AsyncSession | None = None,
) -> FastAPI:
    """A fresh app configured through the environment, as on a real boot.

    Lifespan does not run under ``ASGITransport``, so the state the routes read
    is wired explicitly: settings, a fresh rate limiter (per-app, so budgets
    never leak between tests) and the failing engine used by ``/health``. A
    ``session`` is only needed by routes that touch the database.
    """
    monkeypatch.setenv("CLIENT_IP_SOURCE", source)
    monkeypatch.setenv("CLIENT_IP_XFF_HOPS", str(hops))

    app = create_app()
    app.state.settings = Settings()
    app.state.rate_limiter = RateLimiter()
    app.state.engine = _UnavailableEngine()

    if session is not None:

        async def _override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_db_session] = _override_session

    _mount_probe(app)
    return app


def asgi_client(app: FastAPI, socket_ip: str = SOCKET_IP) -> AsyncClient:
    """In-memory ASGI client whose TCP peer address is ``socket_ip``."""
    transport = ASGITransport(app=app, client=(socket_ip, 51234))
    return AsyncClient(transport=transport, base_url="http://test")
