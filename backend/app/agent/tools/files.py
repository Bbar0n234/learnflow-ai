"""Agent-facing file tools over the workspace file layer (ADR-032, T1.3).

`read_file`/`write_file`/`list_files` are the agent's only direct filesystem
surface: everything below goes through `Workspace` (`app/storage/workspace.py`),
which owns path resolution against the two allowed roots (the caller's
project workspace, rw, and the shared `/skills` library, ro) and the
security log on a denied path. `create_artifact` (pre-T1.3) is gone — saving
a deliverable is now just `write_file` into `artifacts/`; whether a given
write produced an artifact event is decided by path, not by which tool ran
(design-brief § Контракты файловых инструментов).
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Any, cast

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime

from app.storage.workspace import (
    Workspace,
    WorkspacePathError,
    artifact_type,
    to_artifact_path,
)

# Sentinel default for the injected `runtime` param of every tool below — same
# reasoning and mechanism as `load_skill` (`app/agent/tools/skills.py`,
# `conventions/agent.md` § «Инъектируемый ToolRuntime-параметр tool'а»): the
# LLM-facing schema/injection machinery only excludes a param whose annotation
# is *exactly* `ToolRuntime` (`ToolRuntime | None` breaks JSON Schema
# generation), so a real default is required for direct `tool.ainvoke(...)`
# calls without a full agent runtime (unit tests) to still work — the
# sentinel keeps the annotation exact while its runtime value is `None`,
# handled explicitly by `_project_id` below.
_NO_RUNTIME: ToolRuntime = cast("ToolRuntime", None)


def _project_id(runtime: ToolRuntime) -> str:
    if runtime is None or runtime.context is None:
        raise RuntimeError("File tools require AgentContext but none was provided")
    return runtime.context.project_id


def make_file_tools(workspace: Workspace) -> list[BaseTool]:
    """Create `read_file`/`write_file`/`list_files`, bound to `workspace`."""

    @tool
    async def read_file(path: str, runtime: ToolRuntime = _NO_RUNTIME) -> str:
        """Read a text file from the project workspace or the shared skills library.

        Args:
            path: Path to the file, relative to the workspace root (e.g.
                "artifacts/summary.md", "uploads/lecture.pdf"), or an absolute
                "/skills/..." path to read a skill's own file.
        """
        project_id = _project_id(runtime)
        try:
            result = await asyncio.to_thread(workspace.read_text, project_id, path)
        except WorkspacePathError as exc:
            return f"Error: access denied for '{path}' ({exc.reason})."
        except FileNotFoundError:
            return f"Error: file '{path}' not found."
        except IsADirectoryError:
            return f"Error: '{path}' is a directory, not a file."

        if result.content is None:
            return "Error: binary file, use media endpoint."
        if result.truncated:
            return (
                f"{result.content}\n\n[Content truncated: file exceeds the read limit.]"
            )
        return result.content

    @tool(response_format="content_and_artifact")
    async def write_file(
        path: str, content: str, runtime: ToolRuntime = _NO_RUNTIME
    ) -> tuple[str, list[dict[str, Any]]]:
        """Write a text file into the project workspace, creating parent directories.

        Overwrite is silent (normal working-directory semantics). Writing
        into `artifacts/` is how you save a deliverable for the user — a plain
        write, not a separate "create artifact" action; writing anywhere else
        in the workspace is just working memory for later `read_file`/
        `execute_code` calls. Binary artifacts (images, generated files) are
        not produced this way — they come out of a code-execution job or
        `generate_image`.

        Args:
            path: Path to write, relative to the workspace root (e.g.
                "artifacts/summary.md"). Only the project workspace is
                writable — /skills is read-only.
            content: Full text content to write.
        """
        project_id = _project_id(runtime)
        try:
            result = await asyncio.to_thread(
                workspace.write_text, project_id, path, content
            )
        except WorkspacePathError as exc:
            return f"Error: access denied for '{path}' ({exc.reason}).", []
        except IsADirectoryError:
            return f"Error: '{path}' is a directory, not a file.", []

        text = f"File written: '{path}' ({result.kind})"
        artifact_path = to_artifact_path(path)
        if artifact_path is None:
            return text, []

        item: dict[str, Any] = {
            "path": artifact_path,
            "title": PurePosixPath(path).name,
            "type": artifact_type(path),
            "kind": result.kind,
        }
        if result.diff is not None:
            item["diff"] = {"added": result.diff.added, "removed": result.diff.removed}
        return text, [item]

    @tool
    async def list_files(
        path: str = ".",
        recursive: bool = False,
        runtime: ToolRuntime = _NO_RUNTIME,
    ) -> str:
        """List a directory's contents in the project workspace or /skills.

        Args:
            path: Directory to list, relative to the workspace root. Defaults
                to the workspace root itself.
            recursive: List subdirectories' contents too, not just the
                immediate children.
        """
        project_id = _project_id(runtime)
        try:
            entries = await asyncio.to_thread(
                workspace.list_dir, project_id, path, recursive=recursive
            )
        except WorkspacePathError as exc:
            return f"Error: access denied for '{path}' ({exc.reason})."
        except NotADirectoryError:
            return f"Error: '{path}' is not a directory."

        if not entries:
            return "(empty directory)"
        return "\n".join(f"{e.path}/" if e.is_dir else e.path for e in entries)

    return [read_file, write_file, list_files]
