"""Agent-facing execution tools over the executor service (ADR-031, T1.4).

`run_command`/`execute_code` are the agent's only way to run code: both send
a shell command to the executor's `POST /jobs` (`app.infra.executor`) and
turn whatever changed under `artifacts/` while the job ran into the same
`content_and_artifact` envelope `write_file` uses (design-brief § Executor:
"новые/изменённые в artifacts/ → SSE artifact_created/updated" is decided by
a before/after diff of that zone, not by anything the executor reports).

`execute_code` is a specialization of the same job-running path: the code
goes into a scratch file inside the workspace (through the file layer, so it
gets the same tmp-prefix hiding as `write_file`'s atomic-write half) and the
job's `cmd` runs it with the image's system Python — never `python -c`,
so a traceback stays readable and the code isn't squeezed through an argv
length limit. The scratch file is addressed by a path relative to the job's
cwd (the workspace root) because the backend's absolute path doesn't exist
inside the job's mount namespace, and it is deleted in a `finally` so it
never lingers as agent-visible clutter.

A non-zero exit code or an in-job timeout is not this module's concern to
raise on — the executor already decided that outcome, and it comes back as
ordinary tool text (stdout/stderr/exit_code) for the agent to read and fix
its own code. Only a transport-layer failure to reach the executor at all
(`ExecutorUnavailableError`) gets special in-band phrasing, so the agent
doesn't mistake infrastructure being down for a bug in what it wrote.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import PurePosixPath
from typing import Any, cast
from uuid import uuid4

from langchain_core.tools import BaseTool, tool
from langfuse import get_client
from langgraph.prebuilt import ToolRuntime

from app.agent.text_limits import truncate
from app.config import Settings
from app.infra.executor import ExecutorUnavailableError, JobResult, run_job
from app.storage.workspace import (
    TMP_FILE_PREFIX,
    ArtifactDiffEntry,
    Workspace,
    artifact_type,
)

# Same sentinel/mechanism as `files.py` (`conventions/agent.md` § «Инъектируемый
# ToolRuntime-параметр tool'а»), duplicated per module by project precedent
# (`skills.py`, `files.py`) rather than shared — each tool module owns its own
# copy so the exact annotation `ToolRuntime` (not `ToolRuntime | None`) stays
# next to the tools it guards.
_NO_RUNTIME: ToolRuntime = cast("ToolRuntime", None)

_UNAVAILABLE_MESSAGE = (
    "Error: execution runtime unavailable. This is an infrastructure "
    "problem, not an error in the submitted code — do not try to fix the "
    "code in response; retry later or tell the user execution is "
    "temporarily unavailable."
)


def _project_id(runtime: ToolRuntime) -> str:
    if runtime is None or runtime.context is None:
        raise RuntimeError("Execution tools require AgentContext but none was provided")
    return runtime.context.project_id


def make_execution_tools(
    workspace: Workspace,
    settings: Settings,
    *,
    langfuse_enabled: bool = False,
) -> list[BaseTool]:
    """Create `run_command`/`execute_code`, bound to `workspace`/`settings`."""

    @tool(response_format="content_and_artifact")
    async def run_command(
        cmd: str, runtime: ToolRuntime = _NO_RUNTIME
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run a bash command in the project workspace via the execution runtime.

        The command runs with the workspace as its current directory, in an
        isolated sandbox with no network access and no ability to reach
        other projects' files. Use this for shell tools baked into the
        execution image (pandoc, ffmpeg-style conversions, etc.) — for
        running Python code, prefer `execute_code`, which handles quoting
        and long code for you.

        Args:
            cmd: The shell command to run (e.g. "pandoc notes.md -o notes.docx").
        """
        project_id = _project_id(runtime)
        return await _run_job(
            workspace,
            settings,
            project_id=project_id,
            cmd=cmd,
            display_header=f"$ {cmd}",
            span_name="run_command",
            langfuse_enabled=langfuse_enabled,
        )

    @tool(response_format="content_and_artifact")
    async def execute_code(
        code: str, runtime: ToolRuntime = _NO_RUNTIME
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run Python code in the project workspace via the execution runtime.

        The code runs with the workspace as its current directory, in an
        isolated sandbox with no network access — packages available are
        whatever the execution image ships (data-science stack, no runtime
        installs). Print anything you want to see; the sandbox does not
        return values, only stdout/stderr/exit code. Files written into
        `artifacts/` during the run are reported back as artifacts.

        Args:
            code: Python source to execute.
        """
        project_id = _project_id(runtime)
        scratch_name = f"{TMP_FILE_PREFIX}{uuid4().hex}.py"
        await asyncio.to_thread(workspace.write_text, project_id, scratch_name, code)
        try:
            return await _run_job(
                workspace,
                settings,
                project_id=project_id,
                cmd=f"python {scratch_name}",
                display_header="Code executed.",
                span_name="execute_code",
                langfuse_enabled=langfuse_enabled,
            )
        finally:
            scratch_path = workspace.resolve_path(project_id, scratch_name, write=True)
            await asyncio.to_thread(scratch_path.unlink, missing_ok=True)

    return [run_command, execute_code]


async def _run_job(
    workspace: Workspace,
    settings: Settings,
    *,
    project_id: str,
    cmd: str,
    display_header: str,
    span_name: str,
    langfuse_enabled: bool,
) -> tuple[str, list[dict[str, Any]]]:
    """Shared job-running path for `run_command`/`execute_code`.

    Ensures the project workspace directory exists before `POST /jobs` — all
    workspace `mkdir`s happen on the backend side, never the executor's,
    because the directory must be owned by the job's uid for gVisor to allow
    writes to it (spike finding, single-uid requirement) — then snapshots
    `artifacts/` before and after the job to turn whatever changed into the
    same artifact envelope `write_file` produces.
    """
    await asyncio.to_thread(_ensure_workspace_dir, workspace, project_id)

    before = await asyncio.to_thread(workspace.snapshot_artifacts, project_id)
    try:
        result = await _run_job_traced(
            settings,
            project_id=project_id,
            cmd=cmd,
            timeout=settings.executor_job_timeout_seconds,
            span_name=span_name,
            langfuse_enabled=langfuse_enabled,
        )
    except ExecutorUnavailableError:
        return _UNAVAILABLE_MESSAGE, []

    after = await asyncio.to_thread(workspace.snapshot_artifacts, project_id)
    # Pure in-memory dict comparison, no filesystem I/O — unlike the
    # snapshot calls above, this doesn't need a thread.
    diff_entries = workspace.diff_artifacts(before, after)

    text = _format_result_text(display_header, result)
    return text, [_artifact_item(entry) for entry in diff_entries]


def _ensure_workspace_dir(workspace: Workspace, project_id: str) -> None:
    workspace.resolve_path(project_id, ".", write=True).mkdir(
        parents=True, exist_ok=True
    )


async def _run_job_traced(
    settings: Settings,
    *,
    project_id: str,
    cmd: str,
    timeout: float,
    span_name: str,
    langfuse_enabled: bool,
) -> JobResult:
    """`run_job`, wrapped in a fail-safe Langfuse span carrying exit_code + duration.

    No LLM generation happens here, so the span is `as_type="span"` (same
    choice as the guard spans in `security/observer.py`), not `"generation"`
    — there is no cost to attach. Span setup is isolated in its own
    `contextlib.suppress` so a Langfuse outage falls back to an untraced
    call instead of skipping the job (same fail-safe posture as every other
    manual-observation call site in this codebase, conventions.md §
    Восстановление → fail-safe); once the job has actually run, `obs.update`
    is separately suppressed so a tracing error can never cause the job to
    be re-run through a retry path — there is no retry path here, this is
    strictly single-shot.
    """
    if not langfuse_enabled:
        return await run_job(settings, project_id=project_id, cmd=cmd, timeout=timeout)

    obs_cm: Any = None
    with contextlib.suppress(Exception):
        obs_cm = get_client().start_as_current_observation(
            as_type="span", name=span_name, input=cmd
        )
    if obs_cm is None:
        return await run_job(settings, project_id=project_id, cmd=cmd, timeout=timeout)

    start = time.monotonic()
    with obs_cm as obs:
        result = await run_job(
            settings, project_id=project_id, cmd=cmd, timeout=timeout
        )
        with contextlib.suppress(Exception):
            obs.update(
                output={"exit_code": result.exit_code},
                metadata={"duration_ms": round((time.monotonic() - start) * 1000)},
            )
    return result


def _format_result_text(header: str, result: JobResult) -> str:
    parts = [header, f"exit_code: {result.exit_code}"]
    if result.stdout:
        parts.append(f"stdout:\n{result.stdout}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr}")
    text, truncated = truncate("\n".join(parts))
    if truncated:
        text += "\n\n[Output truncated: exceeds the display limit.]"
    return text


def _artifact_item(entry: ArtifactDiffEntry) -> dict[str, Any]:
    item: dict[str, Any] = {
        "path": entry.path,
        "title": PurePosixPath(entry.path).name,
        "type": artifact_type(entry.path),
        "kind": entry.kind,
    }
    if entry.diff is not None:
        item["diff"] = {"added": entry.diff.added, "removed": entry.diff.removed}
    return item
