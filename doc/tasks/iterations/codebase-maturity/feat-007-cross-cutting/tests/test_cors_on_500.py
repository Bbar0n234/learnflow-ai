"""FIX-1 (code-review): generic-500 responses must carry CORS headers.

Empirical regression guard for the middleware-ordering fix in both services.

Root cause: the generic-500 handler middleware was registered AFTER
CORSMiddleware, which (Starlette: last add_middleware = outermost) placed it
OUTSIDE CORS. A 500 produced there shipped without Access-Control-Allow-Origin,
breaking F-API-01 / OQ-2 for both backend and siem-service. The fix registers
CORS LAST so it wraps the generic handler; the 500 response then flows back out
through CORS and receives the header.

These tests build each app via its real create_app(), attach a route that
raises a bare Exception, and assert the 500 response carries
access-control-allow-origin for an allowed Origin. TestClient is used WITHOUT
the lifespan context manager so no DB/Redis connection is attempted.
"""

import os
import sys
from pathlib import Path

# Settings() (called at create_app time) requires jwt secrets.
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("SIEM_JWT_SECRET", "test-secret")

# conftest.py already adds backend/ to sys.path; add siem-service/ too.
_ROOT = Path(__file__).resolve().parents[6]
_SIEM_DIR = _ROOT / "services" / "siem-service"
if str(_SIEM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIEM_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app as create_backend_app  # noqa: E402
from siem_service.main import create_app as create_siem_app  # noqa: E402

ALLOWED_ORIGIN = "http://localhost:5173"


def _attach_boom_route(app: FastAPI) -> None:
    """Add a route that raises, placed first so it wins over any catch-all."""

    async def _boom() -> dict[str, str]:
        raise RuntimeError("boom")

    app.add_api_route("/__boom", _boom, methods=["GET"])
    # Ensure it matches before a frontend catch-all (`/{full_path:path}`).
    app.router.routes.insert(0, app.router.routes.pop())


def _assert_cors_on_500(app: FastAPI) -> None:
    _attach_boom_route(app)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/__boom", headers={"Origin": ALLOWED_ORIGIN})

    assert resp.status_code == 500, resp.status_code
    # The load-bearing assertion: CORS header present on the 500.
    assert resp.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN, (
        "500 response missing Access-Control-Allow-Origin: "
        f"{dict(resp.headers)}"
    )


def test_backend_generic_500_carries_cors_headers() -> None:
    _assert_cors_on_500(create_backend_app())


def test_siem_generic_500_carries_cors_headers() -> None:
    _assert_cors_on_500(create_siem_app())
