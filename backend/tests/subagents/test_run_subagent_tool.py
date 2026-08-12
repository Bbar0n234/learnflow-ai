"""Unit: `run_subagent`'s input side after the move to workspace paths (T1.5).

The tool's own job is narrow — fetch the referenced input documents and turn
runner errors into text the model can read — and this suite is about the fetch,
which changed identity in this iteration: inputs are workspace paths resolved
through the file layer, not PG artifact UUIDs. Two properties carry the
contract. It is *all-or-nothing*: if any path cannot be read, no subagent runs
at all, because a silently partial input would make the subagent answer about a
document it never saw. And it is *project-scoped through the file layer*, so a
traversal path is refused by the same barrier the file tools sit behind — the
tool has no ``project_id`` parameter for the model to aim elsewhere.

The runner is a recording stub (the subagent graph, model and prompts are its
own suites' subject); the workspace is a real directory tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from app.agent.subagents import (
    SubagentDocument,
    SubagentRunner,
    UnknownSubagentTypeError,
)
from app.agent.tools.subagents import make_run_subagent_tool
from app.storage.workspace import Workspace
from langchain_core.tools import BaseTool, StructuredTool
from learnflow_testing.workspace import (
    OTHER_PROJECT_ID,
    PROJECT_ID,
    build_workspace,
    runtime,
    write_file,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    return tmp_path / "workspaces"


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    file_layer, _, _ = build_workspace(tmp_path)
    return file_layer


@pytest.fixture
def project_dir(workspace: Workspace, workspaces_root: Path) -> Path:
    path = workspaces_root / PROJECT_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


class RecordingRunner:
    """Stub `SubagentRunner`: records the run it was asked for, or raises."""

    def __init__(
        self, *, reply: str = "subagent answer", raises: Exception | None = None
    ) -> None:
        self.reply = reply
        self.raises = raises
        self.runs: list[tuple[str, str, list[SubagentDocument]]] = []

    async def run(
        self,
        agent_type: str,
        task: str,
        documents: list[SubagentDocument],
        **_kwargs: Any,
    ) -> str:
        self.runs.append((agent_type, task, documents))
        if self.raises is not None:
            raise self.raises
        return self.reply


def _tool(workspace: Workspace, runner: RecordingRunner) -> BaseTool:
    return make_run_subagent_tool(workspace, cast("SubagentRunner", runner), [])


async def _call(tool: BaseTool, **kwargs: Any) -> Any:
    coroutine = cast("StructuredTool", tool).coroutine
    assert coroutine is not None
    return await coroutine(**kwargs)


async def test_run_subagent_passes_the_referenced_file_content_to_the_subagent(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/draft.md", "# Draft\nbody")
    runner = RecordingRunner()

    result = await _call(
        _tool(workspace, runner),
        agent_type="judge",
        task="review it",
        input_artifact_paths=["artifacts/draft.md"],
        runtime=runtime(),
    )

    assert result == "subagent answer"
    documents = runner.runs[0][2]
    assert [(d.id, d.title, d.content) for d in documents] == [
        ("artifacts/draft.md", "draft.md", "# Draft\nbody")
    ]


async def test_run_subagent_keeps_the_order_of_the_requested_paths(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/a.md", "A")
    write_file(project_dir / "artifacts/b.md", "B")
    runner = RecordingRunner()

    await _call(
        _tool(workspace, runner),
        agent_type="judge",
        task="compare",
        input_artifact_paths=["artifacts/b.md", "artifacts/a.md"],
        runtime=runtime(),
    )

    assert [d.id for d in runner.runs[0][2]] == ["artifacts/b.md", "artifacts/a.md"]


async def test_run_subagent_without_paths_runs_on_the_task_alone(
    workspace: Workspace, project_dir: Path
) -> None:
    runner = RecordingRunner()

    await _call(
        _tool(workspace, runner),
        agent_type="web-research",
        task="find sources",
        runtime=runtime(),
    )

    assert runner.runs[0][2] == []


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("artifacts/missing.md", id="missing-file"),
        pytest.param("/etc/passwd", id="absolute-escape"),
        pytest.param("../../etc/passwd", id="traversal"),
        pytest.param(f"../{OTHER_PROJECT_ID}/artifacts/secret.md", id="other-project"),
        pytest.param("artifacts", id="directory"),
    ],
)
async def test_run_subagent_refuses_the_whole_call_on_an_unreadable_path(
    workspace: Workspace,
    project_dir: Path,
    workspaces_root: Path,
    tmp_path: Path,
    path: str,
) -> None:
    # All-or-nothing: a partially loaded input would have the subagent answer
    # about a document nobody gave it.
    #
    # Every parameter has to fail for its own reason, so each escape gets a
    # *readable file waiting at the end of it*: the neighbouring project's
    # secret, and — for the relative climb — a file at exactly the place
    # `../..` lands (`<tmp>/etc/passwd`, two levels above the project
    # directory). Without that bait the traversal parameter would pass merely
    # because nothing exists up there, i.e. on `FileNotFoundError` rather than
    # on the barrier, and a barrier that stopped refusing would keep it green.
    write_file(project_dir / "artifacts/ok.md", "readable")
    write_file(workspaces_root / OTHER_PROJECT_ID / "artifacts/secret.md", "их данные")
    write_file(tmp_path / "etc/passwd", "root:x:0:0")
    runner = RecordingRunner()

    result = await _call(
        _tool(workspace, runner),
        agent_type="judge",
        task="review",
        input_artifact_paths=["artifacts/ok.md", path],
        runtime=runtime(),
    )

    assert result.startswith("Error: could not load input artifact(s)")
    assert runner.runs == []


async def test_run_subagent_does_not_leak_another_projects_content_in_the_error(
    workspace: Workspace, project_dir: Path, workspaces_root: Path
) -> None:
    write_file(
        workspaces_root / OTHER_PROJECT_ID / "artifacts/secret.md", "TOP SECRET BODY"
    )
    runner = RecordingRunner()

    result = await _call(
        _tool(workspace, runner),
        agent_type="judge",
        task="review",
        input_artifact_paths=[f"../{OTHER_PROJECT_ID}/artifacts/secret.md"],
        runtime=runtime(),
    )

    assert "TOP SECRET BODY" not in result


async def test_run_subagent_refuses_a_binary_input_file(
    workspace: Workspace, project_dir: Path
) -> None:
    (project_dir / "artifacts").mkdir(parents=True)
    (project_dir / "artifacts/cover.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff")
    runner = RecordingRunner()

    result = await _call(
        _tool(workspace, runner),
        agent_type="judge",
        task="review",
        input_artifact_paths=["artifacts/cover.png"],
        runtime=runtime(),
    )

    assert result.startswith("Error: could not load input artifact(s)")
    assert runner.runs == []


async def test_run_subagent_reports_an_unknown_agent_type_as_text(
    workspace: Workspace, project_dir: Path
) -> None:
    # A bad `agent_type` is the model's mistake to correct, not a tool failure.
    runner = RecordingRunner(raises=UnknownSubagentTypeError("nope", ["judge"]))

    result = await _call(
        _tool(workspace, runner), agent_type="nope", task="t", runtime=runtime()
    )

    assert "nope" in result
