"""The second barrier in front of `POST /jobs` — the shared secret.

The `exec` network segment is not the whole story: `/jobs` runs arbitrary code
and takes `project_id` as a plain request field, so a caller that reaches the
port without the backend's secret would get code execution plus rw access to
every project's workspace. What is pinned here is that the barrier holds for
the three cases that matter (no header, wrong token, right token) and that it
stops exactly at `/jobs` — compose's healthcheck has no secret to present.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from executor.config import Settings
from httpx import AsyncClient
from structlog.testing import capture_logs

from tests import AUTH_TOKEN

_JOB = {"project_id": "p1", "cmd": "echo hi"}


@pytest.mark.integration
async def test_post_jobs_without_credentials_is_rejected(
    make_client: Callable[..., AsyncClient], settings: Settings
) -> None:
    """No `Authorization` header at all — the pre-fix behaviour, now a 401."""
    client = make_client(settings, authenticated=False)

    response = await client.post("/jobs", json=_JOB)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.integration
async def test_post_jobs_with_a_wrong_token_is_rejected(
    make_client: Callable[..., AsyncClient], settings: Settings
) -> None:
    client = make_client(settings, authenticated=False)

    response = await client.post(
        "/jobs", json=_JOB, headers={"Authorization": f"Bearer {AUTH_TOKEN}-nope"}
    )

    assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.parametrize(
    "header",
    [
        pytest.param(f"Basic {AUTH_TOKEN}", id="wrong-scheme"),
        pytest.param(AUTH_TOKEN, id="bare-token-no-scheme"),
        pytest.param("Bearer", id="scheme-without-token"),
    ],
)
async def test_post_jobs_with_a_malformed_authorization_header_is_rejected(
    make_client: Callable[..., AsyncClient], settings: Settings, header: str
) -> None:
    """The right secret in the wrong envelope is still a rejection.

    Otherwise the check would depend on how the header happens to parse rather
    than on the token itself.
    """
    client = make_client(settings, authenticated=False)

    response = await client.post("/jobs", json=_JOB, headers={"Authorization": header})

    assert response.status_code == 401


@pytest.mark.integration
async def test_post_jobs_with_the_shared_secret_runs_the_job(
    client: AsyncClient,
) -> None:
    """The positive case — the `client` fixture carries the header."""
    response = await client.post("/jobs", json=_JOB)

    assert response.status_code == 200
    assert response.json() == {"stdout": "hi\n", "stderr": "", "exit_code": 0}


@pytest.mark.integration
async def test_health_needs_no_credentials(
    make_client: Callable[..., AsyncClient], settings: Settings
) -> None:
    """compose's healthcheck holds no secret — `/health` must stay open."""
    client = make_client(settings, authenticated=False)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.integration
async def test_a_rejection_is_logged_with_its_reason(
    make_client: Callable[..., AsyncClient], settings: Settings
) -> None:
    """A rejected caller is a security event, not a silent 401.

    The reason distinguishes "nobody wired the header" from "the two ends'
    tokens disagree" — the same rejection to the caller, two different fixes
    for the operator.
    """
    client = make_client(settings, authenticated=False)

    with capture_logs() as logs:
        await client.post("/jobs", json=_JOB)
        await client.post("/jobs", json=_JOB, headers={"Authorization": "Bearer wrong"})

    assert [
        (entry["event"], entry["log_level"], entry["reason"]) for entry in logs
    ] == [
        ("executor auth rejected", "warning", "missing_credentials"),
        ("executor auth rejected", "warning", "token_mismatch"),
    ]


@pytest.mark.integration
async def test_a_rejected_job_never_reaches_the_runner(
    make_client: Callable[..., AsyncClient],
    settings: Settings,
    workspace: object,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The barrier is in front of execution, not next to it.

    A 401 that still ran the command would defeat the entire point, and a
    status-code assertion alone would not notice.
    """
    marker = tmp_path_factory.mktemp("marker") / "ran"
    client = make_client(settings, authenticated=False)

    await client.post("/jobs", json={"project_id": "p1", "cmd": f"touch {marker}"})

    assert not marker.exists()
