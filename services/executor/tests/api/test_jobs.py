"""`POST /jobs` — the whole public surface of the executor.

This is the contract the backend's tool wrapper is written against: one endpoint,
a body carrying `project_id` plus exactly one of `cmd`/`code`, and a response of
exactly `{stdout, stderr, exit_code}`. The split that matters here is *whose*
failure it is — a job that exits non-zero or overruns its deadline is a 200 with
diagnostics (the agent reads it and fixes its code), while a malformed request
or an unknown project is a 4xx (the caller is wrong).

Jobs run unsandboxed in these tests (see `tests/conftest.py`); what is asserted
is the HTTP contract on top of the runner, not the isolation underneath it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from executor.config import Settings
from httpx import AsyncClient
from structlog.testing import capture_logs


@pytest.mark.integration
async def test_post_jobs_runs_command_and_returns_fixed_fields(
    client: AsyncClient,
) -> None:
    """The response shape is a cross-track contract — three fields, no more.

    T1's tool wrapper reads exactly these; an extra field would be silently
    ignored, a missing one would break the wrapper at runtime.
    """
    response = await client.post("/jobs", json={"project_id": "p1", "cmd": "echo hi"})

    assert response.status_code == 200
    assert response.json() == {"stdout": "hi\n", "stderr": "", "exit_code": 0}


@pytest.mark.integration
async def test_post_jobs_runs_command_through_a_shell(client: AsyncClient) -> None:
    """`cmd` is a shell line, not an argv — pipes and redirects are the point."""
    response = await client.post(
        "/jobs",
        json={"project_id": "p1", "cmd": "echo one && echo two | tr a-z A-Z"},
    )

    assert response.json()["stdout"] == "one\nTWO\n"


@pytest.mark.integration
async def test_post_jobs_keeps_the_scrubbed_path_of_the_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shell does not get to rebuild the job's `PATH`.

    A login shell would source `/etc/profile`, which on Debian overwrites `PATH`
    — the scrubbed environment would then hold only by accident, and the job
    would resolve interpreters from the image instead of the service venv.
    """
    monkeypatch.setenv("PATH", "/nonexistent-service-path")

    response = await client.post(
        "/jobs", json={"project_id": "p1", "cmd": "echo $PATH"}
    )

    assert "/nonexistent-service-path" not in response.json()["stdout"]
    assert response.json()["stdout"].endswith(":/usr/local/bin:/usr/bin:/bin\n")


@pytest.mark.integration
async def test_post_jobs_failing_job_is_a_200_with_diagnostics(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/jobs", json={"project_id": "p1", "cmd": "echo nope >&2; exit 42"}
    )

    assert response.status_code == 200
    assert response.json()["exit_code"] == 42
    assert response.json()["stderr"] == "nope\n"


@pytest.mark.integration
async def test_post_jobs_timed_out_job_is_a_200_with_diagnostics(
    client: AsyncClient,
) -> None:
    """A deadline hit is reported in-band, on the same three fields.

    `JobResponse` has no `timed_out` flag by contract, so the diagnostics have
    to travel in `stderr` — that is what the agent ends up reading.
    """
    response = await client.post(
        "/jobs", json={"project_id": "p1", "cmd": "sleep 30", "timeout": 0.5}
    )

    assert response.status_code == 200
    assert "exceeded timeout" in response.json()["stderr"]
    assert response.json()["exit_code"] != 0


@pytest.mark.integration
async def test_post_jobs_timeout_above_ceiling_is_clamped_and_warned(
    make_client: Callable[..., AsyncClient],
    make_settings: Callable[..., Settings],
) -> None:
    """The service ceiling wins over a caller asking for more.

    It is a backstop, not a second source of truth (the backend's own deadline
    is supposed to sit below it) — so it also has to be visible when it fires,
    otherwise a misconfigured backend just looks flaky.
    """
    settings = make_settings(max_timeout_seconds=1)
    client = make_client(settings)

    with capture_logs() as logs:
        response = await client.post(
            "/jobs", json={"project_id": "p1", "cmd": "sleep 30", "timeout": 600}
        )

    assert "exceeded timeout of 1" in response.json()["stderr"]
    clamped = [entry for entry in logs if entry["event"] == "timeout clamped"]
    assert len(clamped) == 1
    assert clamped[0]["log_level"] == "warning"
    assert clamped[0]["requested_timeout"] == 600
    assert clamped[0]["clamped_timeout"] == 1


@pytest.mark.integration
async def test_post_jobs_negative_timeout_is_clamped_to_zero_and_warned(
    client: AsyncClient,
) -> None:
    """The clamp holds at the bottom too, and says so.

    A negative deadline is a caller bug (a subtraction that went past zero in
    T1's budget arithmetic), and its effect is loud: the job is killed the
    instant it starts. Silently floored, that reads as "the executor kills
    everything"; the WARNING plus the in-band diagnostics name the real cause.
    """
    with capture_logs() as logs:
        response = await client.post(
            "/jobs", json={"project_id": "p1", "cmd": "sleep 30", "timeout": -1}
        )

    assert response.status_code == 200
    assert "exceeded timeout of 0.0" in response.json()["stderr"]
    clamped = [entry for entry in logs if entry["event"] == "timeout clamped"]
    assert len(clamped) == 1
    assert clamped[0]["requested_timeout"] == -1
    assert clamped[0]["clamped_timeout"] == 0.0


@pytest.mark.integration
async def test_post_jobs_timeout_within_ceiling_is_not_warned(
    client: AsyncClient,
) -> None:
    with capture_logs() as logs:
        await client.post(
            "/jobs", json={"project_id": "p1", "cmd": "echo ok", "timeout": 2}
        )

    assert [entry for entry in logs if entry["event"] == "timeout clamped"] == []


@pytest.mark.integration
async def test_post_jobs_without_timeout_falls_back_to_the_service_default(
    make_client: Callable[..., AsyncClient],
    make_settings: Callable[..., Settings],
) -> None:
    """An omitted timeout is the service default — and it is enforced."""
    settings = make_settings(default_timeout_seconds=1)
    client = make_client(settings)

    with capture_logs() as logs:
        response = await client.post(
            "/jobs", json={"project_id": "p1", "cmd": "sleep 30"}
        )

    assert "exceeded timeout of 1" in response.json()["stderr"]
    assert [entry for entry in logs if entry["event"] == "timeout clamped"] == []


@pytest.mark.integration
async def test_post_jobs_code_branch_executes_python_source(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/jobs",
        json={"project_id": "p1", "code": "print('from code branch')"},
    )

    assert response.status_code == 200
    assert response.json()["stdout"] == "from code branch\n"
    assert response.json()["exit_code"] == 0


@pytest.mark.integration
async def test_post_jobs_code_branch_reports_traceback_of_broken_source(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/jobs", json={"project_id": "p1", "code": "raise ValueError('bad')"}
    )

    assert response.status_code == 200
    assert response.json()["exit_code"] != 0
    assert "ValueError: bad" in response.json()["stderr"]


@pytest.mark.integration
async def test_post_jobs_code_branch_leaves_no_temporary_files_behind(
    client: AsyncClient,
    workspace: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The source file is scratch space, not the agent's memory.

    It lives outside the workspace so the job's own directory stays clean (the
    agent lists it and reads it back), and it is removed once the job is done so
    the service does not accumulate them.

    The job prints its own `__file__` first, and that is not decoration: it is
    what proves the redirect took. Asserting only "the scratch directory is
    empty" would stay green if the handler stopped honouring `tempfile.tempdir`
    (a switch to `NamedTemporaryFile(dir=…)`, say) — the file would pile up in
    the real `/tmp` while the test watched an empty directory it owned alone.
    """
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    response = await client.post(
        "/jobs", json={"project_id": "p1", "code": "print(__file__)"}
    )

    source_path = response.json()["stdout"].strip()
    assert source_path.startswith(f"{scratch}/"), (
        f"source file was written outside the observed directory: {source_path}"
    )
    assert list(scratch.iterdir()) == []
    assert list(workspace.iterdir()) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"project_id": "p1"}, "neither code nor cmd"),
        (
            {"project_id": "p1", "cmd": "echo hi", "code": "print(1)"},
            "both code and cmd",
        ),
        ({"cmd": "echo hi"}, "no project_id"),
    ],
)
async def test_post_jobs_malformed_body_is_rejected(
    client: AsyncClient, body: dict[str, str], reason: str
) -> None:
    """Exactly one of `code`/`cmd` — enforced by the schema, so a plain 422."""
    response = await client.post("/jobs", json=body)

    assert response.status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize("project_id", ["../etc", ""])
async def test_post_jobs_unsafe_project_id_is_rejected_with_400(
    client: AsyncClient, project_id: str
) -> None:
    """A traversal attempt is a bad request, never a 500.

    The barrier turns the sandbox subsystem's own exceptions into status codes;
    a 500 here would mean an unhandled exception leaked out of the domain layer.
    Two values, not the whole rejection table: which strings count as unsafe is
    decided (and exhaustively tested) in `tests/sandbox/test_resolve_workspace.py`
    — all of them reach HTTP by the single path asserted here, so repeating the
    table would only make the same barrier fire more times.
    """
    response = await client.post(
        "/jobs", json={"project_id": project_id, "cmd": "echo hi"}
    )

    assert response.status_code == 400


@pytest.mark.unit
async def test_post_jobs_unknown_project_is_rejected_with_404(
    client: AsyncClient, workspaces_root: Path
) -> None:
    response = await client.post(
        "/jobs", json={"project_id": "never-created", "cmd": "echo hi"}
    )

    assert response.status_code == 404
    assert not (workspaces_root / "never-created").exists()
