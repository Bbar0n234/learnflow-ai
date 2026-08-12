"""Smoke: the executor app builds and exposes its two endpoints.

Cheap boot check — the service has no lifespan, no database and no clients, so
`create_app()` succeeding with the expected surface is genuinely all there is to
verify at this level. `/health` is what compose's healthcheck polls.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from executor.config import Settings
from executor.main import create_app
from httpx import AsyncClient


@pytest.mark.unit
def test_create_app_registers_health_and_jobs_routes() -> None:
    app = create_app()

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    assert {"/health", "/jobs"} <= paths


@pytest.mark.unit
async def test_health_endpoint_reports_ok(
    make_client: Callable[..., AsyncClient], make_settings: Callable[..., Settings]
) -> None:
    # Explicitly sandboxed settings: the suite's default runs jobs bare (see
    # `tests/conftest.py`), which is exactly the degraded state below.
    client = make_client(make_settings(sandbox_enabled=True))

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "sandbox": "enabled"}


@pytest.mark.unit
async def test_health_reports_a_disabled_sandbox_as_degradation(
    make_client: Callable[..., AsyncClient], make_settings: Callable[..., Settings]
) -> None:
    """`EXECUTOR_SANDBOX_ENABLED=false` has to be visible from outside.

    Without this the only trace of a service running with no isolation at all
    is its log stream — and logs are what nobody reads until after the
    incident. `/health` is polled by compose and by whatever watches the
    deployment.
    """
    client = make_client(make_settings(sandbox_enabled=False))

    response = await client.get("/health")

    assert response.json() == {"status": "ok", "sandbox": "disabled"}


def _emitted_lines(captured: str) -> list[dict[str, object]]:
    """Parse the service's own JSON log lines out of captured stdout.

    `create_app()` calls `configure_logging()`, which re-`structlog.configure`s
    the process — that replaces whatever `capture_logs()` installed, so the
    startup lines can only be read where they are actually written: stdout,
    through `PrintLoggerFactory`.
    """
    return [json.loads(line) for line in captured.splitlines() if line.strip()]


@pytest.mark.unit
def test_create_app_logs_an_error_when_the_sandbox_is_disabled(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Startup ERROR, not a WARNING lost in per-job noise.

    The kill-switch removes the entire isolation of a service whose only job
    is isolation, so the line an operator sees on boot has to be at the level
    that gets alerted on.
    """
    monkeypatch.setenv("EXECUTOR_SANDBOX_ENABLED", "false")

    create_app()

    errors = [
        entry
        for entry in _emitted_lines(capsys.readouterr().out)
        if entry["level"] == "error"
    ]
    assert len(errors) == 1
    assert "sandbox disabled" in str(errors[0]["event"])
    assert errors[0]["sandbox_enabled"] is False


@pytest.mark.unit
def test_create_app_stays_quiet_when_the_sandbox_is_enabled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The default path must not cry wolf — otherwise the ERROR means nothing."""
    create_app()

    lines = _emitted_lines(capsys.readouterr().out)
    assert lines != []
    assert [entry for entry in lines if entry["level"] == "error"] == []
