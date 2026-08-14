"""Unit: the executor HTTP client (``app/infra/executor.py``).

The executor is the one genuinely external collaborator of this track, so it
is doubled at the transport seam (``httpx.MockTransport``) — no socket, no
service. What the suite pins is the shape of the request the backend sends
(the cross-track contract `POST /jobs {project_id, cmd, timeout}`), the client
deadline it waits under, and — the part that actually matters for the agent —
*which* failures become `ExecutorUnavailableError`. That distinction is a
product decision, not plumbing: an unreachable executor must be reported as
infrastructure being down so the agent stops trying to "fix" its code, while a
non-2xx answer means we built a bad request and has to surface as the ordinary
error it is, not be masked as an outage.

The shared secret of the `exec` segment is pinned here too — that the header
goes out at all, that the backend refuses to start without the token, and that
an auth rejection leaves an explicit ERROR behind instead of reaching the
operator as an unexplained tool failure.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from app.config import Settings
from app.infra.executor import ExecutorUnavailableError, run_job
from pydantic import ValidationError
from structlog.testing import capture_logs

pytestmark = pytest.mark.unit

_BASE_URL = "http://executor.test:8002"
_TOKEN = "shared-secret-of-the-exec-segment"


def _settings(grace: int = 10) -> Settings:
    return Settings(
        executor_base_url=_BASE_URL,
        executor_client_timeout_grace_seconds=grace,
        executor_auth_token=_TOKEN,
    )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> dict[str, Any]:
    """Route the client's requests into `handler`; capture its constructor kwargs.

    `run_job` builds its own `AsyncClient`, so the seam is the class itself —
    swapped for the duration of the test (monkeypatch restores it) by a factory
    that pins a `MockTransport` onto the real client.
    """
    real_client = httpx.AsyncClient
    captured: dict[str, Any] = {}

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        captured.update(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return captured


async def test_run_job_posts_the_contract_body_and_returns_the_job_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(
            200, json={"stdout": "42\n", "stderr": "", "exit_code": 0}
        )

    _install_transport(monkeypatch, handler)

    result = await run_job(
        _settings(), project_id="p1", cmd="python main.py", timeout=60
    )

    assert seen["url"] == f"{_BASE_URL}/jobs"
    assert seen["json"] == {
        "project_id": "p1",
        "cmd": "python main.py",
        "timeout": 60,
    }
    assert (result.stdout, result.stderr, result.exit_code) == ("42\n", "", 0)


def test_settings_refuse_to_build_without_the_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `EXECUTOR_AUTH_TOKEN` — no backend (conventions.md § Секреты и fail-fast).

    The alternative — an empty default — would send jobs with an empty Bearer
    token and only fail on the executor side, or, in a deployment where the
    executor also defaulted, would quietly run with no authentication at all.
    """
    monkeypatch.delenv("EXECUTOR_AUTH_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings()


async def test_run_job_presents_the_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The executor rejects an unsigned job — the header is not optional.

    Without it the `exec` network segment would be the only thing standing
    between anything that reaches the port and arbitrary code execution with
    rw access to every project's workspace.
    """
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"stdout": "", "stderr": "", "exit_code": 0})

    _install_transport(monkeypatch, handler)

    await run_job(_settings(), project_id="p1", cmd="true", timeout=5)

    assert seen["authorization"] == f"Bearer {_TOKEN}"


@pytest.mark.parametrize("status_code", [401, 403])
async def test_run_job_logs_an_auth_rejection_before_surfacing_it(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    """A rejected token is a misconfiguration, and must not be a silent one.

    The agent still sees the ordinary tool error (this is not an outage to
    mask behind "runtime unavailable"), but the operator gets the actual
    cause — the two ends' `EXECUTOR_AUTH_TOKEN` values disagree.
    """
    _install_transport(
        monkeypatch, lambda _r: httpx.Response(status_code, text="unauthorized")
    )

    with capture_logs() as logs, pytest.raises(httpx.HTTPStatusError):
        await run_job(_settings(), project_id="p1", cmd="true", timeout=5)

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert len(errors) == 1
    assert "EXECUTOR_AUTH_TOKEN" in errors[0]["event"]
    assert errors[0]["status_code"] == status_code


async def test_run_job_waits_the_job_deadline_plus_the_configured_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The executor answers a timed-out job only after its own kill grace, so a
    # client deadline equal to the job deadline would turn every job timeout
    # into a false "runtime unavailable".
    captured = _install_transport(
        monkeypatch,
        lambda _r: httpx.Response(
            200, json={"stdout": "", "stderr": "", "exit_code": 0}
        ),
    )

    await run_job(_settings(grace=7), project_id="p1", cmd="true", timeout=60)

    assert captured["timeout"] == 67


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(httpx.ConnectError("connection refused"), id="connect-refused"),
        pytest.param(httpx.ReadTimeout("timed out"), id="read-timeout"),
        pytest.param(httpx.ConnectTimeout("timed out"), id="connect-timeout"),
    ],
)
async def test_run_job_turns_a_transport_failure_into_unavailable(
    monkeypatch: pytest.MonkeyPatch, error: httpx.RequestError
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    _install_transport(monkeypatch, handler)

    with pytest.raises(ExecutorUnavailableError):
        await run_job(_settings(), project_id="p1", cmd="true", timeout=5)


async def test_run_job_logs_a_warning_when_the_executor_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _install_transport(monkeypatch, handler)

    with capture_logs() as logs, pytest.raises(ExecutorUnavailableError):
        await run_job(_settings(), project_id="p1", cmd="true", timeout=5)

    assert [(e["event"], e["log_level"], e["project_id"]) for e in logs] == [
        ("executor unreachable", "warning", "p1")
    ]


async def test_run_job_lets_a_non_2xx_response_surface_as_an_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 4xx/5xx means the request we built is wrong — a bug to surface through
    # the ordinary tool-error path, not an outage to hide behind "unavailable".
    _install_transport(monkeypatch, lambda _r: httpx.Response(500, text="boom"))

    with pytest.raises(httpx.HTTPStatusError):
        await run_job(_settings(), project_id="p1", cmd="true", timeout=5)
