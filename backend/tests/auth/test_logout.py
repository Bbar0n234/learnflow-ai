"""Logout: revoke the presented refresh token and clear the cookie.

Two layers, by what the transactional harness can observe:

- **HTTP contract** (200 / cookie cleared / idempotent) is asserted over the
  real ``/auth/logout`` flow.
- **Revocation effect** is asserted at the service layer (``AuthService.logout``
  — a public entry point — against real Postgres). The logout *handler* issues a
  bare ``UPDATE`` with no follow-up flush; under the shared-session,
  rollback-isolated harness (no per-request commit, unlike production's
  ``get_db_session``) that write is not surfaced to a *subsequent* HTTP request.
  Production commits per request, so the revoke persists there — a harness
  boundary, not a product gap (see runlog/auth.md). The "a revoked token is
  rejected on reuse" behaviour is covered end-to-end by the rotation/replay
  path, which flushes (see test_refresh.py).
"""

from __future__ import annotations

import pytest
from app.config import Settings
from app.repositories.refresh_token import RefreshTokenRepository
from app.services.auth import AuthService
from app.services.security import hash_raw_token
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth._helpers import register


@pytest.mark.integration
async def test_logout_returns_ok_and_clears_cookie(auth_client: AsyncClient) -> None:
    await register(auth_client)

    # The refresh cookie sits in the jar (path /api/auth) and is sent here.
    response = await auth_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["detail"] == "Logged out"
    assert "max-age=0" in response.headers.get("set-cookie", "").lower()


@pytest.mark.integration
async def test_logout_without_cookie_is_idempotent(auth_client: AsyncClient) -> None:
    auth_client.cookies.clear()

    response = await auth_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json()["detail"] == "Logged out"


@pytest.mark.integration
async def test_logout_revokes_the_presented_refresh_token(
    db_session: AsyncSession, settings: Settings
) -> None:
    service = AuthService(db_session, settings)
    _user, _access, refresh_raw = await service.register("logout-user", "password123")

    await service.logout(refresh_raw)

    db_session.expire_all()
    stored = await RefreshTokenRepository(db_session).get_by_hash(
        hash_raw_token(refresh_raw)
    )
    assert stored is not None
    assert stored.revoked_at is not None


@pytest.mark.integration
async def test_logout_with_unknown_token_is_a_noop(
    db_session: AsyncSession, settings: Settings
) -> None:
    service = AuthService(db_session, settings)

    # No matching row — must not raise, nothing to revoke.
    await service.logout("not-a-real-token")
