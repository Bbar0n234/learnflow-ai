"""Smoke: the executor app builds and exposes its two endpoints.

Cheap boot check — the service has no lifespan, no database and no clients, so
`create_app()` succeeding with the expected surface is genuinely all there is to
verify at this level. `/health` is what compose's healthcheck polls.
"""

from __future__ import annotations

import pytest
from executor.main import create_app
from httpx import AsyncClient


@pytest.mark.unit
def test_create_app_registers_health_and_jobs_routes() -> None:
    app = create_app()

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    assert {"/health", "/jobs"} <= paths


@pytest.mark.unit
async def test_health_endpoint_reports_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
