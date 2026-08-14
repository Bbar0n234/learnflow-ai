"""Unit: the agent's file tools (``app/agent/tools/files.py``).

`read_file`/`write_file`/`list_files` are the agent's whole filesystem
surface. The tools themselves are thin, and that is exactly the contract worth
pinning: they must translate every filesystem reality — a denied path, a
missing file, a binary blob, a directory — into a *readable error string the
model can act on*, never an exception that would escape into the graph's
generic error handler, and `write_file` must additionally decide whether the
write produced an artifact (path inside `artifacts/`) and whether it created
or updated one.

The workspace collaborator is real (a directory tree under ``tmp_path``) —
sociable by default, and faking it here would fake the layer that decides the
answers. The only double is the injected ``ToolRuntime``, which carries the
`project_id` the agent is never allowed to name itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from app.agent.tools.files import make_file_tools
from app.storage.workspace import TMP_FILE_PREFIX, Workspace
from langchain_core.tools import BaseTool, StructuredTool
from learnflow_testing.workspace import OTHER_PROJECT_ID, runtime, write_file

pytestmark = pytest.mark.unit


def _tool(workspace: Workspace, name: str) -> BaseTool:
    tools = {t.name: t for t in make_file_tools(workspace)}
    return tools[name]


async def _call(tool: BaseTool, **kwargs: Any) -> Any:
    """Drive the raw coroutine: ``ToolRuntime`` is injected by the graph, not by us."""
    coroutine = cast("StructuredTool", tool).coroutine
    assert coroutine is not None
    return await coroutine(**kwargs)


# --- read_file --------------------------------------------------------------


async def test_read_file_returns_the_file_contents(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "uploads/lecture.md", "# Лекция 1")

    result = await _call(
        _tool(workspace, "read_file"), path="uploads/lecture.md", runtime=runtime()
    )

    assert result == "# Лекция 1"


async def test_read_file_over_the_limit_is_marked_as_truncated(
    make_workspace: Any, project_dir: Path
) -> None:
    # The cap applies to what actually enters the model's context; the marker
    # is what tells the agent the file continues beyond what it sees.
    workspace = make_workspace(read_limit_chars=4)
    write_file(project_dir / "notes.md", "0123456789")

    result = await _call(
        _tool(workspace, "read_file"), path="notes.md", runtime=runtime()
    )

    assert result.startswith("0123")
    assert "truncated" in result.lower()


async def test_read_file_of_a_skills_file_is_allowed(
    workspace: Workspace, project_dir: Path, skills_root: Path
) -> None:
    write_file(skills_root / "alpha/reference.md", "skill reference")

    result = await _call(
        _tool(workspace, "read_file"),
        path=f"{skills_root}/alpha/reference.md",
        runtime=runtime(),
    )

    assert result == "skill reference"


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("/etc/passwd", id="absolute-escape"),
        pytest.param("../../etc/passwd", id="traversal"),
        pytest.param(f"../{OTHER_PROJECT_ID}/artifacts/secret.md", id="other-project"),
    ],
)
async def test_read_file_of_a_denied_path_returns_an_error_string(
    workspace: Workspace, project_dir: Path, path: str
) -> None:
    # A refusal must reach the model as text it can reason about, not as an
    # exception the graph would report as a tool failure.
    result = await _call(_tool(workspace, "read_file"), path=path, runtime=runtime())

    assert result.startswith("Error: access denied")


async def test_read_file_of_a_missing_file_returns_an_error_string(
    workspace: Workspace, project_dir: Path
) -> None:
    result = await _call(
        _tool(workspace, "read_file"), path="nope.md", runtime=runtime()
    )

    assert result == "Error: file 'nope.md' not found."


async def test_read_file_of_a_directory_returns_an_error_string(
    workspace: Workspace, project_dir: Path
) -> None:
    (project_dir / "artifacts").mkdir()

    result = await _call(
        _tool(workspace, "read_file"), path="artifacts", runtime=runtime()
    )

    assert result == "Error: 'artifacts' is a directory, not a file."


async def test_read_file_of_a_binary_file_points_at_the_media_endpoint(
    workspace: Workspace, project_dir: Path
) -> None:
    (project_dir / "cover.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff")

    result = await _call(
        _tool(workspace, "read_file"), path="cover.png", runtime=runtime()
    )

    assert result == "Error: binary file, use media endpoint."


async def test_read_file_without_an_agent_context_raises(workspace: Workspace) -> None:
    # `project_id` comes from the graph's AgentContext — a call without one is
    # a wiring bug, not a model mistake, and must not silently read anything.
    with pytest.raises(RuntimeError):
        await _call(_tool(workspace, "read_file"), path="notes.md")


# --- write_file -------------------------------------------------------------


async def test_write_file_into_artifacts_reports_a_created_artifact(
    workspace: Workspace, project_dir: Path
) -> None:
    text, artifacts = await _call(
        _tool(workspace, "write_file"),
        path="artifacts/summary.md",
        content="# Summary",
        runtime=runtime(),
    )

    assert "created" in text
    assert artifacts == [
        {"path": "summary.md", "title": "summary.md", "type": "md", "kind": "created"}
    ]
    assert (project_dir / "artifacts/summary.md").read_text() == "# Summary"


async def test_write_file_into_a_subdirectory_keeps_the_path_relative_to_artifacts(
    workspace: Workspace, project_dir: Path
) -> None:
    # The artifact's identity is its path below `artifacts/` (ADR-032) — the
    # zone prefix never appears in the envelope the UI addresses files by.
    _, artifacts = await _call(
        _tool(workspace, "write_file"),
        path="artifacts/lecture-1/slides.md",
        content="# Slides",
        runtime=runtime(),
    )

    assert artifacts[0]["path"] == "lecture-1/slides.md"
    assert artifacts[0]["title"] == "slides.md"


async def test_write_file_over_an_existing_artifact_reports_an_update_with_a_diff(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/summary.md", "one\ntwo\n")

    _, artifacts = await _call(
        _tool(workspace, "write_file"),
        path="artifacts/summary.md",
        content="one\ntwo\nthree\n",
        runtime=runtime(),
    )

    assert artifacts[0]["kind"] == "updated"
    assert artifacts[0]["diff"] == {"added": 1, "removed": 0}


async def test_write_file_outside_artifacts_produces_no_artifact(
    workspace: Workspace, project_dir: Path
) -> None:
    # Working memory is an ordinary write: whether an artifact event follows
    # is decided by the path, not by which tool ran.
    _, artifacts = await _call(
        _tool(workspace, "write_file"),
        path="scratch/plan.md",
        content="plan",
        runtime=runtime(),
    )

    assert artifacts == []
    assert (project_dir / "scratch/plan.md").read_text() == "plan"


async def test_write_file_to_a_denied_path_returns_an_error_and_no_artifact(
    workspace: Workspace, project_dir: Path
) -> None:
    text, artifacts = await _call(
        _tool(workspace, "write_file"),
        path=f"../{OTHER_PROJECT_ID}/artifacts/planted.md",
        content="payload",
        runtime=runtime(),
    )

    assert text.startswith("Error: access denied")
    assert artifacts == []


async def test_write_file_into_the_skills_library_is_refused(
    workspace: Workspace, project_dir: Path, skills_root: Path
) -> None:
    write_file(skills_root / "alpha/SKILL.md", "# Alpha")

    text, artifacts = await _call(
        _tool(workspace, "write_file"),
        path=f"{skills_root}/alpha/SKILL.md",
        content="hacked",
        runtime=runtime(),
    )

    assert text.startswith("Error: access denied")
    assert artifacts == []
    assert (skills_root / "alpha/SKILL.md").read_text() == "# Alpha"


async def test_write_file_without_an_agent_context_raises(
    workspace: Workspace,
) -> None:
    with pytest.raises(RuntimeError):
        await _call(_tool(workspace, "write_file"), path="a.md", content="x")


# --- list_files -------------------------------------------------------------


async def test_list_files_marks_directories_with_a_trailing_slash(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/notes.md", "x")
    write_file(project_dir / "artifacts/lecture-1/slides.md", "y")

    result = await _call(
        _tool(workspace, "list_files"), path="artifacts", runtime=runtime()
    )

    assert result == "lecture-1/\nnotes.md"


async def test_list_files_recursive_reaches_nested_paths(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "artifacts/lecture-1/slides.md", "y")

    result = await _call(
        _tool(workspace, "list_files"),
        path="artifacts",
        recursive=True,
        runtime=runtime(),
    )

    assert result == "lecture-1/\nlecture-1/slides.md"


async def test_list_files_hides_the_file_layers_scratch_files(
    workspace: Workspace, project_dir: Path
) -> None:
    # `execute_code` parks its source in the workspace under this prefix; the
    # agent must not see its own plumbing listed back to it.
    write_file(project_dir / "notes.md", "x")
    write_file(project_dir / f"{TMP_FILE_PREFIX}deadbeef.py", "print(1)")

    result = await _call(_tool(workspace, "list_files"), path=".", runtime=runtime())

    assert result == "notes.md"


async def test_list_files_of_an_empty_directory_says_so(
    workspace: Workspace, project_dir: Path
) -> None:
    result = await _call(_tool(workspace, "list_files"), path=".", runtime=runtime())

    assert result == "(empty directory)"


async def test_list_files_of_a_denied_path_returns_an_error_string(
    workspace: Workspace, project_dir: Path
) -> None:
    result = await _call(
        _tool(workspace, "list_files"), path="../..", runtime=runtime()
    )

    assert result.startswith("Error: access denied")


async def test_list_files_of_a_file_returns_an_error_string(
    workspace: Workspace, project_dir: Path
) -> None:
    write_file(project_dir / "notes.md", "x")

    result = await _call(
        _tool(workspace, "list_files"), path="notes.md", runtime=runtime()
    )

    assert result == "Error: 'notes.md' is not a directory."
