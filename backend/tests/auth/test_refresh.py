"""Refresh-token rotation, replay detection, and rejection paths.

The whole flow runs against real Postgres: rotation revokes the old token,
reuse of a superseded token trips replay detection and revokes every session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.refresh_token import RefreshToken
from app.services.security import generate_refresh_token, hash_raw_token
from httpx import AsyncClient
from learnflow_testing.factories import UserFactory
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth._helpers import DEFAULT_NAME, do_refresh, refresh_value, register


@pytest.mark.integration
async def test_refresh_rotates_and_new_token_chains(auth_client: AsyncClient) -> None:
    registered = await register(auth_client)
    r1 = refresh_value(registered)
    assert r1 is not None

    first = await do_refresh(auth_client, r1)

    assert first.status_code == 200
    access_token = first.json()["access_token"]
    assert access_token

    # The reissued access token is not just non-empty — it authenticates. Walk
    # /me with it so a "minted but unusable" token (wrong sub, stale secret)
    # cannot pass as a green refresh.
    me = await auth_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me.status_code == 200
    assert me.json()["name"] == DEFAULT_NAME

    r2 = refresh_value(first)
    assert r2 is not None
    assert r2 != r1  # rotated, not reissued

    # The rotated token is itself valid — rotation chains.
    second = await do_refresh(auth_client, r2)
    assert second.status_code == 200


@pytest.mark.integration
async def test_reuse_of_rotated_token_trips_replay_and_revokes_all(
    auth_client: AsyncClient,
) -> None:
    registered = await register(auth_client)
    r1 = refresh_value(registered)
    assert r1 is not None

    rotated = await do_refresh(auth_client, r1)
    r2 = refresh_value(rotated)
    assert r2 is not None

    # Replaying the superseded R1 is detected.
    replay = await do_refresh(auth_client, r1)
    assert replay.status_code == 401
    assert replay.json()["detail"] == "Token reuse detected, all sessions revoked"
    assert "max-age=0" in replay.headers.get("set-cookie", "").lower()

    # Replay revoked every session, so the once-valid R2 is now rejected too.
    after = await do_refresh(auth_client, r2)
    assert after.status_code == 401


@pytest.mark.integration
async def test_refresh_without_cookie_is_unauthorized(
    auth_client: AsyncClient,
) -> None:
    auth_client.cookies.clear()

    response = await auth_client.post("/api/auth/refresh")

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token missing"


@pytest.mark.integration
async def test_refresh_with_unknown_token_is_unauthorized(
    auth_client: AsyncClient,
) -> None:
    response = await do_refresh(auth_client, "not-a-real-token")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"


@pytest.mark.integration
async def test_refresh_with_expired_stored_token_is_unauthorized(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    user = await UserFactory.create()
    raw, token_hash = generate_refresh_token()
    db_session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await db_session.flush()

    response = await do_refresh(auth_client, raw)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"
    # sanity: the hash matched a real row (not the unknown-token path)
    assert hash_raw_token(raw) == token_hash
