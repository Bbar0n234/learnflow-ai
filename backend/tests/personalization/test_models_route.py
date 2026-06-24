"""HTTP integration tests for ``GET /api/models``.

The endpoint paginates the agent config's ``available_models`` list. The
``configured_app`` fixture seeds two models (``gpt-4o``, ``claude-3``); we assert
the list envelope and pagination slicing.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.integration
async def test_list_models_returns_available_models(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {m["name"] for m in body["items"]} == {"gpt-4o", "claude-3"}


@pytest.mark.integration
async def test_list_models_pagination_slices_items(
    api_client: AsyncClient,
) -> None:
    resp = await api_client.get("/api/models", params={"limit": 1, "offset": 0})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # total reflects the full set
    assert len(body["items"]) == 1
    assert body["limit"] == 1
