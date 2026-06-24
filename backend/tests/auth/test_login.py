"""Register + login over the real auth flow (route -> service -> repo -> PG).

Token validity is checked by walking ``/auth/me`` with the issued access token,
not by inspecting the JWT — behaviour through the public interface.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.auth._helpers import (
    DEFAULT_NAME,
    DEFAULT_PASSWORD,
    login,
    refresh_value,
    register,
)


@pytest.mark.integration
async def test_register_new_user_issues_working_access_token(
    auth_client: AsyncClient,
) -> None:
    response = await register(auth_client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert refresh_value(response)  # refresh cookie set

    me = await auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["name"] == DEFAULT_NAME


@pytest.mark.integration
async def test_register_duplicate_name_is_rejected(auth_client: AsyncClient) -> None:
    await register(auth_client)

    response = await register(auth_client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Username already exists"


@pytest.mark.integration
async def test_register_short_password_fails_validation(
    auth_client: AsyncClient,
) -> None:
    response = await register(auth_client, password="short")

    assert response.status_code == 422


@pytest.mark.integration
async def test_login_valid_credentials_issues_working_access_token(
    auth_client: AsyncClient,
) -> None:
    await register(auth_client)

    response = await login(auth_client)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert refresh_value(response)

    me = await auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["name"] == DEFAULT_NAME


@pytest.mark.integration
async def test_login_wrong_password_is_unauthorized(auth_client: AsyncClient) -> None:
    await register(auth_client)

    response = await login(auth_client, password=DEFAULT_PASSWORD + "-wrong")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.integration
async def test_login_unknown_user_is_unauthorized(auth_client: AsyncClient) -> None:
    response = await login(auth_client, name="nobody")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"
