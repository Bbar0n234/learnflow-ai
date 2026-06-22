"""Access-token validation at the auth dependency (api/deps.get_current_user).

Exercised through a protected endpoint (``/auth/me``) so the test asserts the
observable 401 contract, not the decoder internals.
"""

from __future__ import annotations

import uuid

import pytest
from app.config import Settings
from app.services.security import create_access_token
from httpx import AsyncClient


@pytest.mark.integration
async def test_request_without_token_is_unauthorized(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.integration
async def test_request_with_non_bearer_header_is_unauthorized(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get(
        "/api/auth/me", headers={"Authorization": "Token abc"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.integration
async def test_expired_access_token_is_unauthorized(
    auth_client: AsyncClient, settings: Settings
) -> None:
    expired = create_access_token(uuid.uuid4(), settings.jwt_secret, expire_minutes=-1)

    response = await auth_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


@pytest.mark.integration
async def test_wrong_signature_access_token_is_unauthorized(
    auth_client: AsyncClient,
) -> None:
    forged = create_access_token(uuid.uuid4(), "attacker-secret", expire_minutes=30)

    response = await auth_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {forged}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


@pytest.mark.integration
async def test_valid_token_for_missing_user_is_unauthorized(
    auth_client: AsyncClient, settings: Settings
) -> None:
    # Correctly signed and unexpired, but no such user row in the DB.
    token = create_access_token(uuid.uuid4(), settings.jwt_secret, expire_minutes=30)

    response = await auth_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"
