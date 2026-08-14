"""``run_subagent`` tool — thin subagent-as-tool wrapper (feat-011, T1.3/T1.5).

The tool itself does two things a `SubagentRunner` cannot do on its own:
fetch referenced input documents (project-scoped, all-or-nothing) and
translate `SubagentRunner` errors into tool-visible strings. Everything else
— resolving the spec, building the model/prompt, compiling and running the
graph — lives in `SubagentRunner` (`app.agent.subagents.runner`).

Description is assembled once at startup from the subagent registry, same
pattern as the Skills Index (`app.agent.tools.skills.scan_skills_index`):
the model sees the available subagent types (`name: description`) at the
point it picks this tool, not by inference or a separate lookup call.

T1.6: this tool executes inside the main graph's own `ToolNode`, the one
place where a real stream writer and this call's own `call_id` are both
available (`ToolRuntime.stream_writer`/`.tool_call_id`) — both are passed
down to `SubagentRunner.run` so it can wrap the subagent's own tools and
report their execution on the main stream, tagged with `parent_call_id`
(design-brief § "Вложенность субагента").

T1.5: input documents are addressed by workspace path (`input_artifact_paths`)
resolved through the file layer (`Workspace`), not by PG artifact UUID — the
same identity shift `write_file`/`read_file` (T1.3) went through. The
subagent itself is not handed any file tools (design-brief § Инструменты
агента: file access stays out of the v1 subagent tool pool).
"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath

import structlog
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime

from app.agent.config import SubagentSpec
from app.agent.subagents import (
    SubagentDocument,
    SubagentRunner,
    UnknownSubagentTypeError,
)
from app.storage.workspace import Workspace, WorkspacePathError

logger = structlog.get_logger()


def build_run_subagent_description(registry: list[SubagentSpec]) -> str:
    """Build the ``run_subagent`` tool description from the spec registry.

    One line per type (``name: description``), resolved once at startup —
    an unrecognized type is caught at call time (`UnknownSubagentTypeError`),
    this text is what lets the model pick correctly in the first place.
    """
    lines = [f"- {spec.name}: {spec.description}" for spec in registry]
    types_block = "\n".join(lines) if lines else "(none configured)"
    return (
        "Delegate an isolated subtask to a subagent running with a clean "
        "context (no session history — only `task` and, optionally, the "
        "content of `input_artifact_paths` reach it). Pick `agent_type` "
        "from the list below and describe the subtask in `task`.\n\n"
        "If the input is large (e.g. a draft to review), save it as a file "
        "first (`write_file`) and pass its path in `input_artifact_paths` "
        "instead of copying the content into `task` — the subagent "
        "receives the file's content byte-for-byte, so nothing is lost, "
        "and you avoid reproducing the whole text as output tokens. "
        "Multiple paths are injected in the order given. Any path that "
        "cannot be read fails the whole call — no subagent runs with a "
        "partial input.\n\n"
        f"Available subagent types:\n{types_block}"
    )


async def _fetch_documents(
    workspace: Workspace,
    project_id: str,
    artifact_paths: list[str],
) -> tuple[list[SubagentDocument], str | None]:
    """Fetch documents for ``input_artifact_paths``, all-or-nothing.

    Returns ``(documents, None)`` on success, in the caller's path order. If
    any path escapes the project workspace, doesn't exist, or is binary,
    returns ``([], error_string)`` naming every problem path — no partial
    input ever reaches the subagent (design-brief § "Вход субагента").
    """
    problems: list[str] = []
    documents: list[SubagentDocument] = []

    for path in artifact_paths:
        try:
            result = await asyncio.to_thread(workspace.read_text, project_id, path)
        except (WorkspacePathError, FileNotFoundError, IsADirectoryError):
            problems.append(path)
            continue
        if result.content is None:
            problems.append(path)
            continue
        documents.append(
            SubagentDocument(
                id=path, title=PurePosixPath(path).name, content=result.content
            )
        )

    if problems:
        return [], (
            "Error: could not load input artifact(s): "
            f"{', '.join(problems)}. Each path must exist and be a "
            "readable text file in this project's workspace. No subagent "
            "was run."
        )
    return documents, None


def make_run_subagent_tool(
    workspace: Workspace,
    runner: SubagentRunner,
    registry: list[SubagentSpec],
) -> BaseTool:
    """Create the ``run_subagent`` tool bound to the given Runner."""

    description = build_run_subagent_description(registry)

    @tool(description=description)
    async def run_subagent(
        agent_type: str,
        task: str,
        runtime: ToolRuntime,
        input_artifact_paths: list[str] | None = None,
    ) -> str:
        """Delegate an isolated subtask to a subagent with a clean context."""
        if runtime.context is None:
            raise RuntimeError(
                "run_subagent requires AgentContext but none was provided"
            )
        project_id = runtime.context.project_id

        documents: list[SubagentDocument] = []
        if input_artifact_paths:
            documents, error = await _fetch_documents(
                workspace, project_id, input_artifact_paths
            )
            if error is not None:
                logger.info(
                    "run_subagent artifact fetch failed",
                    agent_type=agent_type,
                    problem_count=len(input_artifact_paths),
                )
                return error

        try:
            return await runner.run(
                agent_type,
                task,
                documents,
                config=runtime.config,
                canary_token=runtime.context.canary_token,
                stream_writer=runtime.stream_writer,
                parent_call_id=runtime.tool_call_id,
            )
        except UnknownSubagentTypeError as exc:
            logger.info(
                "run_subagent unknown agent_type",
                agent_type=agent_type,
                available_types=exc.available_types,
            )
            return str(exc)

    return run_subagent
