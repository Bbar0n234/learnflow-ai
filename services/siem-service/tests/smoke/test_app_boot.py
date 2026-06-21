"""Smoke: the siem-service app constructs and registers its routes.

Cheap boot check — builds ``create_app()`` without running lifespan (no Redis /
Postgres connection) and asserts the surface is wired.
"""

from __future__ import annotations

import pytest
from siem_service.main import create_app


@pytest.mark.unit
def test_create_app_registers_routes() -> None:
    app = create_app()

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    assert "/health" in paths
