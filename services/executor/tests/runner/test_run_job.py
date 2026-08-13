"""Running a job: deadline, kill chain, output ceiling, scrubbed environment.

These tests start real processes (unsandboxed — see `tests/conftest.py`), which
is the point: a deadline that fires, a process group that dies with its
grandchildren, and a pipe that is drained rather than buffered are properties of
the operating system, not of a data structure. Everything the runner promises is
observable from its return value — a job that fails, overruns or floods its
output is a `JobResult`, never an exception.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from executor.config import Settings
from executor.runner import run_job
from structlog.testing import capture_logs

# The environment the runner builds for a job — the same five variables
# `executor.sandbox` bakes into the sandboxed job via `--setenv`.
EXPECTED_JOB_ENV_KEYS = {"PATH", "HOME", "LANG", "MPLCONFIGDIR", "XDG_CACHE_HOME"}


@pytest.mark.integration
def test_run_job_successful_command_returns_stdout_and_zero_exit(
    workspace: Path, settings: Settings
) -> None:
    result = run_job(workspace, ["bash", "-c", "echo hello"], 5.0, settings)

    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.timed_out is False


@pytest.mark.integration
def test_run_job_failing_command_reports_exit_code_and_stderr(
    workspace: Path, settings: Settings
) -> None:
    """A job's own failure is a result the backend can hand to the agent.

    Non-zero exits are the agent's working loop (write code, read the error, fix
    it), so they must not surface as an exception or an empty stderr.
    """
    result = run_job(workspace, ["bash", "-c", "echo boom >&2; exit 3"], 5.0, settings)

    assert result.exit_code == 3
    assert result.stderr == "boom\n"
    assert result.timed_out is False


@pytest.mark.integration
def test_run_job_runs_inside_the_workspace_directory(
    workspace: Path, settings: Settings
) -> None:
    """Relative paths in a job resolve against its own workspace."""
    result = run_job(
        workspace, ["bash", "-c", "pwd; echo written > artifact.txt"], 5.0, settings
    )

    assert result.stdout.strip() == str(workspace)
    assert (workspace / "artifact.txt").read_text() == "written\n"


@pytest.mark.integration
def test_run_job_environment_is_scrubbed_of_service_variables(
    workspace: Path, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job sees a built-from-scratch environment, not the service's own.

    The executor holds no stack secrets by design, but "no secrets today" is not
    a boundary — the boundary is that the job's environment is constructed, so
    anything added to the service's environment later still never reaches it.

    Bounded from both sides on purpose. The upper bound is the isolation
    invariant (nothing extra reaches the job); the lower bound is a drift guard
    — `runner._job_env()` is the second, otherwise unchecked copy of the set
    `sandbox.build_job_argv` bakes into `--setenv`, and a variable quietly
    dropped from one of them (no `MPLCONFIGDIR` → matplotlib writes to a
    read-only `$HOME`) is a job-time failure nothing else here would catch.
    """
    monkeypatch.setenv("EXECUTOR_CANARY_SECRET", "must-not-leak")
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret@db/learnflow")

    result = run_job(workspace, ["bash", "-c", "env"], 5.0, settings)
    job_env = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )

    assert "must-not-leak" not in result.stdout
    assert set(job_env) >= EXPECTED_JOB_ENV_KEYS
    assert set(job_env) <= EXPECTED_JOB_ENV_KEYS | {
        "PWD",  # set by bash itself, not inherited
        "SHLVL",
        "_",
    }


@pytest.mark.integration
def test_run_job_over_deadline_is_killed_and_reported_as_timed_out(
    workspace: Path, settings: Settings
) -> None:
    """An overrun comes back as a result carrying its own diagnostics.

    The backend turns this into a `ToolMessage` the agent can read; an exception
    here would instead read as an infrastructure failure and send the agent
    retrying the wrong thing.
    """
    started = time.monotonic()
    result = run_job(workspace, ["bash", "-c", "sleep 30"], 0.5, settings)
    elapsed = time.monotonic() - started

    assert result.timed_out is True
    assert result.exit_code < 0
    assert "exceeded timeout" in result.stderr
    assert elapsed < 0.5 + settings.kill_grace_seconds + 5


@pytest.mark.integration
@pytest.mark.slow
def test_run_job_over_deadline_kills_grandchildren(
    workspace: Path, settings: Settings
) -> None:
    """The kill reaches processes the job itself spawned.

    A job is usually a shell that spawns the real work (pandoc, a pipeline);
    killing only the direct child would leave those running against the shared
    volume long after the agent got its answer. Observed through the file the
    grandchild keeps appending to: once the deadline has passed, it must stop
    growing.
    """
    heartbeat = workspace / "heartbeat.txt"
    command = [
        "bash",
        "-c",
        f"(while true; do echo tick >> {heartbeat}; sleep 0.05; done) & wait",
    ]

    result = run_job(workspace, command, 0.5, settings)

    assert result.timed_out is True
    assert heartbeat.exists(), "grandchild never ran — the test proves nothing"
    time.sleep(0.3)
    size_after_kill = heartbeat.stat().st_size
    time.sleep(0.5)
    assert heartbeat.stat().st_size == size_after_kill


@pytest.mark.integration
@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_run_job_output_over_ceiling_is_truncated_with_a_notice(
    workspace: Path, make_settings: Callable[..., Settings], stream: str
) -> None:
    """Flooded output is capped per stream, and the job still finishes.

    The ceiling exists so `cat huge.bin` cannot OOM the service, but a reader
    that stops reading would block the job on a full pipe until the deadline —
    hence the second half of the assertion: normal exit, not a timeout.
    """
    settings = make_settings(max_output_bytes=1024)
    redirect = "" if stream == "stdout" else " >&2"
    command = ["bash", "-c", f"python3 -c \"print('x' * 100000)\"{redirect}"]

    result = run_job(workspace, command, 10.0, settings)
    text = getattr(result, stream)

    assert text.startswith("x" * 1024)
    assert "truncated" in text
    assert len(text) < 2048
    assert result.exit_code == 0
    assert result.timed_out is False


@pytest.mark.integration
def test_run_job_output_within_ceiling_is_returned_verbatim(
    workspace: Path, make_settings: Callable[..., Settings]
) -> None:
    settings = make_settings(max_output_bytes=1024)

    result = run_job(workspace, ["bash", "-c", "echo small"], 5.0, settings)

    assert result.stdout == "small\n"


@pytest.mark.integration
@pytest.mark.slow
def test_run_job_reports_degraded_capture_when_a_process_outlives_the_job(
    workspace: Path, settings: Settings
) -> None:
    """A survivor holding the pipes open costs output, never the response.

    A pipe reaches EOF only once every copy of its write end is closed. Under
    the sandbox the kill-контракт guarantees that (the job is pid 1 of its own
    namespace); on the dev escape hatch used by this suite nothing stops a
    backgrounded process from outliving the job with the pipe inherited. Waiting
    for it would hang the request past the very deadline the runner exists to
    enforce, so the wait is bounded — and because the response carries only
    three fixed fields, the shortfall has to be visible inside them, otherwise
    the agent reads a partial answer as a complete one.
    """
    command = ["bash", "-c", "echo captured; sleep 10 & exit 0"]

    started = time.monotonic()
    with capture_logs() as logs:
        result = run_job(workspace, command, 30.0, settings)
    elapsed = time.monotonic() - started

    assert "captured" in result.stdout, "output produced before the job exited"
    assert "output capture incomplete" in result.stderr
    assert result.exit_code == 0
    assert result.timed_out is False
    assert elapsed < 5, "the runner waited on the survivor instead of giving up"

    finished = [entry for entry in logs if entry["event"] == "job finished"]
    assert finished[0]["output_incomplete"] is True
    assert finished[0]["log_level"] == "warning"


@pytest.mark.integration
def test_run_job_undecodable_output_is_returned_with_replacements(
    workspace: Path, settings: Settings
) -> None:
    """Binary garbage on stdout degrades to replacement characters.

    Job output is untrusted input to the service — a stray `cat` of a PNG must
    not raise `UnicodeDecodeError` inside the request handler.
    """
    result = run_job(workspace, ["bash", "-c", r"printf 'ok\xff\xfe'"], 5.0, settings)

    assert result.stdout.startswith("ok")
    assert "�" in result.stdout
    assert result.exit_code == 0


@pytest.mark.integration
def test_run_job_unlaunchable_command_raises_and_logs_an_error(
    workspace: Path, settings: Settings
) -> None:
    """Failing to *start* a job is an infrastructure failure, not a job result.

    Returning `exit_code != 0` here would tell the agent its code is broken when
    the truth is that the executor's own runtime is missing. This being the
    service's only ERROR line, it is also the only place a traceback can come
    from — hence `exc_info`: `capture_logs` sees the event before the processor
    chain, so the flag here is what `format_exc_info` renders into the
    `exception` field downstream (`tests/observability/test_logging.py`).
    """
    with capture_logs() as logs, pytest.raises(OSError):
        run_job(workspace, ["executor-nonexistent-binary"], 5.0, settings)

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert [entry["event"] for entry in errors] == ["job launch failed"]
    assert errors[0]["exc_info"] is True


@pytest.mark.integration
def test_run_job_logs_outcome_at_warning_when_timed_out(
    workspace: Path, settings: Settings
) -> None:
    """One log line per job, its level carrying the verdict."""
    with capture_logs() as logs:
        run_job(workspace, ["bash", "-c", "sleep 30"], 0.5, settings)

    finished = [entry for entry in logs if entry["event"] == "job finished"]
    assert len(finished) == 1
    assert finished[0]["log_level"] == "warning"
    assert finished[0]["timed_out"] is True
    assert finished[0]["project_id"] == workspace.name


@pytest.mark.integration
def test_run_job_logs_outcome_at_info_when_successful(
    workspace: Path, settings: Settings
) -> None:
    with capture_logs() as logs:
        run_job(workspace, ["bash", "-c", "echo ok"], 5.0, settings)

    finished = [entry for entry in logs if entry["event"] == "job finished"]
    assert len(finished) == 1
    assert finished[0]["log_level"] == "info"
    assert finished[0]["exit_code"] == 0
    assert finished[0]["stdout_truncated"] is False
