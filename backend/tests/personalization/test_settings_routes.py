"""HTTP integration tests for the settings routes.

Driven through the state-enriched ``api_client`` (authenticated, real Postgres
under the handler via the shared transactional session). The resolver reads back
what the handler wrote, so we assert both the stored value and the cascade-
resolved model/source — the response contract — plus the allowed-model guard.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_get_user_settings_defaults_to_config_when_unset(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/users/me/settings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_name"] is None
    assert body["resolved_model"] == "default-model"
    assert body["resolved_source"] == "config"


@pytest.mark.integration
async def test_put_user_settings_persists_and_resolves_to_user_scope(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.put(
        "/api/users/me/settings",
        json={"model_name": "gpt-4o", "extra_body": {"temperature": 0.1}},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["model_name"] == "gpt-4o"
    assert body["extra_body"] == {"temperature": 0.1}
    assert body["resolved_model"] == "gpt-4o"
    assert body["resolved_source"] == "user"


@pytest.mark.integration
async def test_put_user_settings_persists_across_requests(
    api_client: AsyncClient,
) -> None:
    await api_client.put("/api/users/me/settings", json={"model_name": "claude-3"})

    resp = await api_client.get("/api/users/me/settings")

    assert resp.json()["model_name"] == "claude-3"


@pytest.mark.integration
async def test_put_user_settings_rejects_model_outside_allowlist(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.put(
        "/api/users/me/settings", json={"model_name": "not-allowed-model"}
    )

    assert resp.status_code == 422


@pytest.mark.integration
async def test_put_user_settings_null_model_is_allowed(
    api_client: AsyncClient,
) -> None:
    # Clearing the override (None) must not trip the allowlist check.
    resp = await api_client.put("/api/users/me/settings", json={"model_name": None})

    assert resp.status_code == 200
    assert resp.json()["resolved_source"] == "config"
