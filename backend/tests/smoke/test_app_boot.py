"""Smoke: the backend app constructs and registers its routes.

Cheap boot check — builds ``create_app()`` without running lifespan (no network)
and asserts the API surface is wired. Full-lifespan integration is exercised by
the DB/HTTP fixtures.
"""

from __future__ import annotations

import pytest
from app.main import create_app


@pytest.mark.unit
def test_create_app_registers_api_routes() -> None:
    app = create_app()

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    assert "/health" in paths
    assert any(path.startswith("/api/projects") for path in paths)
