"""Logout: revoke the presented refresh token and clear the cookie.

Covered at two layers:

- **HTTP contract** — ``/auth/logout`` returns 200, clears the refresh cookie,
  and is idempotent without one.
- **Revocation, end to end** — after logout, replaying the now-revoked token at
  ``/auth/refresh`` is rejected: it is a known-but-revoked row, so it trips
  replay detection. The logout handler's bare Core ``UPDATE`` (no follow-up
  flush) *is* visible to that subsequent request — the shared, rollback-isolated
  session surfaces the in-session write without a per-request commit, exactly as
  the rotation/replay path does (see test_refresh.py). The earlier suspicion
  that this write was lost on request teardown was a test artifact: the
  path-scoped refresh cookie was simply not delivered to ``/auth/logout``, so no
  revoke ran. The service-layer test below additionally asserts the persisted
  ``revoked_at`` directly.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from app.repositories.refresh_token import RefreshTokenRepository
from app.services.auth import AuthService
from app.services.security import hash_raw_token
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth._helpers import do_refresh, refresh_value, register


@pytest.mark.integration
async def test_logout_then_reusing_refresh_token_is_rejected(
    auth_client: AsyncClient,
) -> None:
    registered = await register(auth_client)
    r1 = refresh_value(registered)
    assert r1 is not None

    # Cookie sent explicitly: the refresh cookie is path-scoped to /api/auth and
    # httpx does not auto-attach it here (same reason do_refresh sends it raw).
    logout = await auth_client.post("/api/auth/logout", cookies={"refresh_token": r1})
    assert logout.status_code == 200

    # The in-session revoke is visible to the next request over the shared
    # session, so presenting the logged-out token now trips replay detection
    # (a known-but-revoked row) instead of rotating a fresh one.
    after = await do_refresh(auth_client, r1)
    assert after.status_code == 401
    assert after.json()["detail"] == "Token reuse detected, all sessions revoked"


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
