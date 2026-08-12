"""Shared helpers for suites that exercise the project workspace file layer.

Three backend scopes drive the same file layer — the workspace suites
themselves, the subagent input tool and image generation — because "where a
path may point" is one decision several tools delegate to. The builders below
are their common ground: a `Workspace` on throwaway roots and the duck-typed
`ToolRuntime` the tools read `project_id` from. They live here rather than in
one scope's ``conftest.py`` because conftest fixtures do not travel sideways,
and importing another scope's conftest would tie three directories together by
code (conventions/testing.md § Расположение: shared test utilities belong to
``packages/testing``).

Like :mod:`learnflow_testing.fakes`, this module imports backend code and is
therefore only importable from a backend test environment — nothing here is
loaded by the pytest plugin entry point.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

from app.storage.workspace import Workspace

if TYPE_CHECKING:
    from langgraph.prebuilt import ToolRuntime

# The project a test acts as, and a neighbour it must never reach into.
PROJECT_ID = "project-1"
OTHER_PROJECT_ID = "project-2"


def build_workspace(
    tmp_path: Path,
    *,
    read_limit_chars: int = 50_000,
    diff_file_limit_bytes: int = 1_000_000,
    diff_total_limit_bytes: int = 10_000_000,
) -> tuple[Workspace, Path, Path]:
    """A `Workspace` on fresh roots under `tmp_path` -> (workspace, ws_root, skills).

    The two roots mirror the two mounts the container gets: a workspaces root
    holding one directory per project, and a read-only skills root. The limits
    are keyword arguments because several suites need them dialled down to a
    few bytes to reach the truncation and oversized-diff branches without
    writing megabytes.
    """
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir(exist_ok=True)
    skills_root = tmp_path / "skills"
    skills_root.mkdir(exist_ok=True)
    return (
        Workspace(
            workspaces_root=workspaces_root,
            skills_root=skills_root,
            read_limit_chars=read_limit_chars,
            diff_file_limit_bytes=diff_file_limit_bytes,
            diff_total_limit_bytes=diff_total_limit_bytes,
        ),
        workspaces_root,
        skills_root,
    )


def write_file(path: Path, content: str) -> Path:
    """Write `content` at `path`, creating parents — plain test-data setup.

    Deliberately not the production ``Workspace.write_text``: arranging a
    fixture through the code under test would make a broken writer look like a
    passing read.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def runtime(project_id: str = PROJECT_ID) -> ToolRuntime:
    """Duck-typed ``ToolRuntime``: the tools only read ``context.project_id``.

    Same shape the other tool suites use (``tests/personalization/
    test_user_memory_tools.py``) — a real ``ToolRuntime`` would need a store
    the file/execution tools never touch. The call-plumbing fields
    (``config``/``stream_writer``/``tool_call_id``) are here for the one tool
    that forwards them downstream (``run_subagent``); the file and execution
    tools read nothing but ``context.project_id``.
    """
    return cast(
        "ToolRuntime",
        SimpleNamespace(
            context=SimpleNamespace(project_id=project_id, canary_token=""),
            config={},
            stream_writer=None,
            tool_call_id="call-1",
        ),
    )


def runtime_without_context() -> ToolRuntime:
    """A runtime the graph handed over without an ``AgentContext``.

    Distinct from "no runtime at all": the injection happened, but the call
    carries no project — a tool must refuse rather than pick a default.
    """
    return cast("ToolRuntime", SimpleNamespace(context=None))
