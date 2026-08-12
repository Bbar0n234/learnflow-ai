"""Sociable-unit: the agent's execution tools (``app/agent/tools/execution.py``).

`run_command`/`execute_code` do three things around a job that this suite
pins. They report a finished job as ordinary tool text — a crashed or
timed-out job is a working cycle for the agent, not a failure to raise on —
while an *unreachable* executor gets its own in-band phrasing so the agent
doesn't go off fixing code that never ran. They turn whatever changed under
`artifacts/` while the job ran into the same artifact envelope `write_file`
produces, decided by a before/after snapshot the backend takes itself, never
by anything the executor reports. And `execute_code` parks the submitted
source in a scratch file inside the workspace, hands the job a path relative
to its cwd (the backend's absolute path does not exist inside the job's mount
namespace), and removes that file whatever the outcome.

The executor is faked at the `run_job` seam — the network boundary, and the
one collaborator that is genuinely external. The fake also stands in for the
job's *side effects*: a real job writes files into the shared volume, so the
fake writes them too, which is what makes the snapshot/diff assertions real
rather than a rehearsal of a mock's return value. The workspace itself is a
real directory tree.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from app.agent.text_limits import TRUNCATION_LIMIT
from app.agent.tools import execution as execution_module
from app.agent.tools.execution import make_execution_tools
from app.config import Settings
from app.infra.executor import ExecutorUnavailableError, JobResult
from app.storage.workspace import TMP_FILE_PREFIX, Workspace
from langchain_core.tools import BaseTool, StructuredTool
from learnflow_testing.workspace import PROJECT_ID, runtime, write_file

pytestmark = pytest.mark.unit


class FakeExecutor:
    """Stands in for the executor service at the `run_job` seam.

    Records the job it was asked to run, optionally performs the filesystem
    side effects a real job would have (that is what the artifacts snapshot
    observes), and returns a programmed result — or raises the transport
    failure the unavailable-executor branch is about.
    """

    def __init__(
        self,
        *,
        result: JobResult | None = None,
        effect: Callable[[], object] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.result = result or JobResult(stdout="", stderr="", exit_code=0)
        self.effect = effect
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self, settings: Settings, *, project_id: str, cmd: str, timeout: float
    ) -> JobResult:
        self.calls.append({"project_id": project_id, "cmd": cmd, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        if self.effect is not None:
            self.effect()
        return self.result


def _tools(
    workspace: Workspace,
    executor: FakeExecutor,
    monkeypatch: pytest.MonkeyPatch,
    *,
    job_timeout: int = 60,
) -> dict[str, BaseTool]:
    monkeypatch.setattr(execution_module, "run_job", executor)
    settings = Settings(executor_job_timeout_seconds=job_timeout)
    return {t.name: t for t in make_execution_tools(workspace, settings)}


async def _call(tool: BaseTool, **kwargs: Any) -> Any:
    coroutine = cast("StructuredTool", tool).coroutine
    assert coroutine is not None
    return await coroutine(**kwargs)


# --- run_command: the job's own outcome -------------------------------------


async def test_run_command_reports_the_command_exit_code_and_streams(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(
        result=JobResult(stdout="pandoc 3.1\n", stderr="", exit_code=0)
    )
    tools = _tools(workspace, executor, monkeypatch)

    text, artifacts = await _call(
        tools["run_command"], cmd="pandoc --version", runtime=runtime()
    )

    assert "$ pandoc --version" in text
    assert "exit_code: 0" in text
    assert "pandoc 3.1" in text
    assert artifacts == []


async def test_run_command_sends_the_command_and_the_configured_deadline(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor()
    tools = _tools(workspace, executor, monkeypatch, job_timeout=45)

    await _call(tools["run_command"], cmd="ls -la", runtime=runtime())

    assert executor.calls == [
        {"project_id": PROJECT_ID, "cmd": "ls -la", "timeout": 45}
    ]


async def test_run_command_reports_a_failed_job_as_a_result_not_an_exception(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A crashed job is the agent's working cycle: it reads stderr and fixes
    # its code. Raising here would surface as a tool failure instead.
    executor = FakeExecutor(
        result=JobResult(stdout="", stderr="Traceback: NameError", exit_code=1)
    )
    tools = _tools(workspace, executor, monkeypatch)

    text, artifacts = await _call(
        tools["run_command"], cmd="python broken.py", runtime=runtime()
    )

    assert "exit_code: 1" in text
    assert "NameError" in text
    assert artifacts == []


async def test_run_command_truncates_an_oversized_job_output(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(
        result=JobResult(stdout="x" * (TRUNCATION_LIMIT * 2), stderr="", exit_code=0)
    )
    tools = _tools(workspace, executor, monkeypatch)

    text, _ = await _call(tools["run_command"], cmd="cat big.txt", runtime=runtime())

    assert "truncated" in text.lower()
    assert len(text) < TRUNCATION_LIMIT * 2


async def test_run_command_reports_an_unreachable_executor_as_infrastructure(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phrasing matters here, not just the fact of an error: the agent must not
    # read an outage as a bug in the code it just submitted.
    executor = FakeExecutor(raises=ExecutorUnavailableError("down"))
    tools = _tools(workspace, executor, monkeypatch)

    text, artifacts = await _call(tools["run_command"], cmd="true", runtime=runtime())

    assert "execution runtime unavailable" in text
    assert "infrastructure" in text
    assert artifacts == []


async def test_run_command_without_an_agent_context_raises(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = _tools(workspace, FakeExecutor(), monkeypatch)

    with pytest.raises(RuntimeError):
        await _call(tools["run_command"], cmd="true")


# --- the artifacts/ diff around the job -------------------------------------


async def test_a_job_writing_into_artifacts_reports_a_created_artifact(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(
        effect=lambda: write_file(project_dir / "artifacts/chart.png", "png-bytes")
    )
    tools = _tools(workspace, executor, monkeypatch)

    _, artifacts = await _call(
        tools["run_command"], cmd="python plot.py", runtime=runtime()
    )

    assert artifacts == [
        {"path": "chart.png", "title": "chart.png", "type": "png", "kind": "created"}
    ]


async def test_a_job_rewriting_an_artifact_reports_an_update_with_a_diff(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(project_dir / "artifacts/notes.md", "one\ntwo\n")
    executor = FakeExecutor(
        effect=lambda: write_file(
            project_dir / "artifacts/notes.md", "one\ntwo\nthree\nfour\n"
        )
    )
    tools = _tools(workspace, executor, monkeypatch)

    _, artifacts = await _call(
        tools["run_command"], cmd="python edit.py", runtime=runtime()
    )

    assert artifacts[0]["kind"] == "updated"
    assert artifacts[0]["diff"] == {"added": 2, "removed": 0}


async def test_a_job_touching_several_artifacts_reports_each_of_them(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One call, N files — the envelope is a list precisely so a render job
    # doesn't have to collapse its output into a single artifact.
    def render() -> None:
        write_file(project_dir / "artifacts/lecture-1/slides.md", "# Slides")
        write_file(project_dir / "artifacts/lecture-1/notes.md", "# Notes")

    tools = _tools(workspace, FakeExecutor(effect=render), monkeypatch)

    _, artifacts = await _call(
        tools["run_command"], cmd="python render.py", runtime=runtime()
    )

    assert sorted(a["path"] for a in artifacts) == [
        "lecture-1/notes.md",
        "lecture-1/slides.md",
    ]


async def test_a_job_writing_outside_artifacts_reports_nothing(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(
        effect=lambda: write_file(project_dir / "work/intermediate.csv", "a,b")
    )
    tools = _tools(workspace, executor, monkeypatch)

    _, artifacts = await _call(
        tools["run_command"], cmd="python prep.py", runtime=runtime()
    )

    assert artifacts == []


async def test_the_workspace_directory_is_created_before_the_job_runs(
    workspace: Workspace, workspaces_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every mkdir happens on the backend side: under gVisor a job may only
    # write into a directory its own uid owns (spike finding), and the
    # executor never creates one.
    seen: list[bool] = []
    executor = FakeExecutor(
        effect=lambda: seen.append((workspaces_root / "fresh-project").is_dir())
    )
    tools = _tools(workspace, executor, monkeypatch)

    await _call(tools["run_command"], cmd="true", runtime=runtime("fresh-project"))

    assert seen == [True]


# --- execute_code: the scratch file -----------------------------------------


async def test_execute_code_runs_the_scratch_file_by_a_path_relative_to_the_cwd(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The backend's absolute path doesn't exist inside the job's mount
    # namespace, so the command must address the file from the workspace cwd.
    executor = FakeExecutor()
    tools = _tools(workspace, executor, monkeypatch)

    await _call(tools["execute_code"], code="print(1)", runtime=runtime())

    cmd = executor.calls[0]["cmd"]
    assert cmd.startswith(f"python {TMP_FILE_PREFIX}")
    assert cmd.endswith(".py")


async def test_execute_code_makes_the_submitted_source_readable_to_the_job(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def read_scratch() -> None:
        scratch = next(project_dir.glob(f"{TMP_FILE_PREFIX}*.py"))
        seen.append(scratch.read_text(encoding="utf-8"))

    tools = _tools(workspace, FakeExecutor(effect=read_scratch), monkeypatch)

    await _call(tools["execute_code"], code="print('hi')", runtime=runtime())

    assert seen == ["print('hi')"]


async def test_execute_code_removes_the_scratch_file_afterwards(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = _tools(workspace, FakeExecutor(), monkeypatch)

    await _call(tools["execute_code"], code="print(1)", runtime=runtime())

    assert list(project_dir.glob(f"{TMP_FILE_PREFIX}*")) == []


async def test_execute_code_removes_the_scratch_file_even_when_the_job_fails(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(raises=ExecutorUnavailableError("down"))
    tools = _tools(workspace, executor, monkeypatch)

    await _call(tools["execute_code"], code="print(1)", runtime=runtime())

    assert list(project_dir.glob(f"{TMP_FILE_PREFIX}*")) == []


async def test_execute_code_does_not_reveal_the_scratch_file_name_to_the_agent(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor = FakeExecutor(result=JobResult(stdout="1\n", stderr="", exit_code=0))
    tools = _tools(workspace, executor, monkeypatch)

    text, _ = await _call(tools["execute_code"], code="print(1)", runtime=runtime())

    assert TMP_FILE_PREFIX not in text
    assert "Code executed." in text


async def test_execute_code_scratch_file_is_not_reported_as_an_artifact(
    workspace: Workspace, project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The scratch file shares the file layer's temp prefix, so neither the
    # artifacts snapshot nor `list_files` ever sees it.
    tools = _tools(workspace, FakeExecutor(), monkeypatch)

    _, artifacts = await _call(
        tools["execute_code"], code="print(1)", runtime=runtime()
    )

    assert artifacts == []


async def test_execute_code_without_an_agent_context_raises(
    workspace: Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    tools = _tools(workspace, FakeExecutor(), monkeypatch)

    with pytest.raises(RuntimeError):
        await _call(tools["execute_code"], code="print(1)")
