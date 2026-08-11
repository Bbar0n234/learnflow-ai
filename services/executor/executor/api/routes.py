"""HTTP surface for job execution — `POST /jobs`.

Synchronous `def` handler by design (conventions/api.md § Блокирующий код):
the job itself is a blocking `subprocess` + pipe-read loop — there is no
true-async equivalent, so FastAPI is left to run it in its threadpool
rather than forcing an artificial `await` somewhere.

Domain failures (`InvalidProjectIdError`, `WorkspaceMissingError`) are
raised by `executor.sandbox.resolve_workspace` and left to propagate — they
are mapped to `400`/`404` by barrier exception handlers registered in
`executor.main`, not caught and re-raised as `HTTPException` here
(conventions.md § Модель ошибок).
"""

import os
import tempfile
from pathlib import Path

import structlog
from fastapi import APIRouter

from executor.api.deps import SettingsDep
from executor.api.schemas import JobRequest, JobResponse
from executor.config import Settings
from executor.runner import run_job
from executor.sandbox import resolve_workspace

logger = structlog.get_logger()

router = APIRouter()

# Fixed in-sandbox destination for the `code` branch — a stable path gives
# readable tracebacks (`File "/tmp/job.py"`) instead of a random mkstemp
# name. Only meaningful when sandboxed: `build_job_argv` remaps the real
# temp file onto it via a ro-bind placed after `--tmpfs /tmp`.
_SANDBOXED_CODE_PATH = "/tmp/job.py"


def _clamp_timeout(timeout: float | None, settings: Settings) -> float:
    """Clamp requested `timeout` into `[0, max_timeout_seconds]`.

    `None` takes the service default — not a clamp, so no warning. An
    out-of-range value logs a WARNING: this ceiling is a defensive backstop,
    not a second source of truth (T1's own backend-deadline must already sit
    at or below `EXECUTOR_MAX_TIMEOUT_SECONDS`).
    """
    if timeout is None:
        return float(settings.default_timeout_seconds)

    clamped = min(max(timeout, 0.0), float(settings.max_timeout_seconds))
    if clamped != timeout:
        logger.warning(
            "timeout clamped",
            requested_timeout=timeout,
            clamped_timeout=clamped,
            max_timeout_seconds=settings.max_timeout_seconds,
        )
    return clamped


@router.post("/jobs")
def create_job(request: JobRequest, settings: SettingsDep) -> JobResponse:
    """Execute a job synchronously inside its project's workspace."""
    workspace = resolve_workspace(request.project_id, settings)
    timeout = _clamp_timeout(request.timeout, settings)

    if request.cmd is not None:
        # Not `-lc`: a login shell sources `/etc/profile`, which on Debian
        # rewrites the job's assembled `PATH` — the scrubbed-env invariant
        # would then hold only by accident.
        command = ["bash", "-c", request.cmd]
        result = run_job(workspace, command, timeout, settings)
        return JobResponse(
            stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code
        )

    # `code` branch: source goes to a temp file outside the workspace so the
    # job's own filesystem stays clean, ro-bound into the sandbox at a fixed
    # path and removed again once the job has finished (or failed to start).
    fd, tmp_path_str = tempfile.mkstemp(suffix=".py", prefix="executor-job-")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w") as tmp_file:
            tmp_file.write(request.code or "")

        if settings.sandbox_enabled:
            command = ["python", _SANDBOXED_CODE_PATH]
            extra_ro_binds = [(str(tmp_path), _SANDBOXED_CODE_PATH)]
        else:
            # Dev escape hatch: no mount namespace exists to remap the
            # fixed alias onto, so the job runs against the real host path.
            command = ["python", str(tmp_path)]
            extra_ro_binds = []

        result = run_job(
            workspace, command, timeout, settings, extra_ro_binds=extra_ro_binds
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return JobResponse(
        stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code
    )
