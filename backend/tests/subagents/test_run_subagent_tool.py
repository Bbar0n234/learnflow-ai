"""Behavior tests for the ``run_subagent`` tool wrapper (feat-011, T1.3).

The tool does two things the ``SubagentRunner`` cannot: fetch referenced
artifacts (project-scoped, all-or-nothing) and translate a spec-resolution
error into a tool-visible string. We drive the tool's ``.coroutine`` directly
with a constructed ``ToolRuntime`` (the injected ``runtime`` arg is excluded
from the public schema — same pattern as the KS/image-generation tool tests).

The artifact fetch runs against **real Postgres** through
``tool_session_factory`` (the tool opens its own session), so ownership
scoping and the not-found/invalid-UUID branches are exercised on the real
repository. The Runner itself is replaced by a recording ``SpyRunner`` — its
job (build model, run graph) reaches the LLM, the painful boundary, and is
covered on its own in ``test_runner.py``; here we assert what the tool hands
it and how it maps its errors.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest
from app.agent.graph import AgentContext
from app.agent.subagents import SubagentDocument, UnknownSubagentTypeError
from app.agent.tools.subagents import make_run_subagent_tool
from app.repositories.artifact import ArtifactRepository
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class SpyRunner:
    """Records ``run`` calls; returns a canned string or raises a set error."""

    def __init__(
        self, *, result: str = "SUBAGENT RESULT", raises: Exception | None = None
    ) -> None:
        self._result = result
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    async def run(
        self,
        agent_type: str,
        task: str,
        documents: list[SubagentDocument] | None = None,
        *,
        config: Any = None,
        canary_token: str = "",
        stream_writer: Any = None,
        parent_call_id: str | None = None,
    ) -> str:
        self.calls.append(
            {
                "agent_type": agent_type,
                "task": task,
                "documents": documents,
                "config": config,
                "canary_token": canary_token,
                "stream_writer": stream_writer,
                "parent_call_id": parent_call_id,
            }
        )
        if self._raises is not None:
            raise self._raises
        return self._result


def _coro(tool: object) -> Callable[..., Awaitable[Any]]:
    return cast(Callable[..., Awaitable[Any]], cast(StructuredTool, tool).coroutine)


def _runtime(
    *,
    project_id: str,
    canary_token: str = "canary-1",
    with_context: bool = True,
    config: dict[str, Any] | None = None,
) -> ToolRuntime[AgentContext | None, dict[str, Any]]:
    context = (
        AgentContext(project_id=project_id, user_id="user-1", canary_token=canary_token)
        if with_context
        else None
    )
    return ToolRuntime(
        state={},
        context=context,
        config=cast(Any, config or {"tags": ["main-graph"]}),
        stream_writer=lambda _: None,
        tool_call_id="call-1",
        store=None,
    )


def _make_tool(
    session_factory: Callable[[], AsyncSession],
    runner: SpyRunner,
    registry: list[Any] | None = None,
) -> Any:
    return make_run_subagent_tool(
        cast(Any, session_factory), cast(Any, runner), registry or []
    )


async def _seed_artifact(
    session: AsyncSession, *, project_id: uuid.UUID, title: str, content: str
) -> uuid.UUID:
    artifact = await ArtifactRepository(session).create(
        project_id=project_id, title=title, type="text", content=content
    )
    return artifact.id


# --- spec-resolution error translation --------------------------------------


async def test_unknown_agent_type_is_returned_as_error_string(
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    runner = SpyRunner(
        raises=UnknownSubagentTypeError("nope", ["general-purpose", "judge"])
    )
    tool = _make_tool(tool_session_factory, runner)

    result = await _coro(tool)(
        agent_type="nope",
        task="task",
        runtime=_runtime(project_id=str(uuid.uuid4())),
    )

    # The tool catches the error and surfaces the type list to the model
    # instead of letting it escape as a generic tool failure.
    assert "nope" in result
    assert "general-purpose" in result and "judge" in result


# --- artifact fetch: all-or-nothing -----------------------------------------


async def test_valid_artifact_is_fetched_and_passed_to_the_runner(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    project = await ProjectFactory.create()
    artifact_id = await _seed_artifact(
        seed_session, project_id=project.id, title="Draft", content="Body text."
    )
    runner = SpyRunner(result="VERDICT")
    tool = _make_tool(tool_session_factory, runner)

    result = await _coro(tool)(
        agent_type="judge",
        task="Review this.",
        input_artifact_ids=[str(artifact_id)],
        runtime=_runtime(project_id=str(project.id)),
    )

    assert result == "VERDICT"
    # The document reached the Runner byte-for-byte, with id/title attribution.
    (call,) = runner.calls
    (doc,) = call["documents"]
    assert (doc.id, doc.title, doc.content) == (
        str(artifact_id),
        "Draft",
        "Body text.",
    )


async def test_foreign_project_artifact_fails_the_whole_call(
    seed_session: AsyncSession,
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    mine = await ProjectFactory.create()
    other = await ProjectFactory.create()
    my_id = await _seed_artifact(
        seed_session, project_id=mine.id, title="Mine", content="ok"
    )
    foreign_id = await _seed_artifact(
        seed_session, project_id=other.id, title="Theirs", content="secret"
    )
    runner = SpyRunner()
    tool = _make_tool(tool_session_factory, runner)

    result = await _coro(tool)(
        agent_type="judge",
        task="Review.",
        input_artifact_ids=[str(my_id), str(foreign_id), "not-a-uuid"],
        runtime=_runtime(project_id=str(mine.id)),
    )

    # All-or-nothing: the error names only the problem ids (foreign + malformed),
    # not the valid one, and no subagent ran with a partial input.
    assert str(foreign_id) in result
    assert "not-a-uuid" in result
    assert str(my_id) not in result
    assert runner.calls == []


async def test_nonexistent_artifact_id_fails_without_running(
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    runner = SpyRunner()
    tool = _make_tool(tool_session_factory, runner)
    missing = str(uuid.uuid4())

    result = await _coro(tool)(
        agent_type="judge",
        task="Review.",
        input_artifact_ids=[missing],
        runtime=_runtime(project_id=str(uuid.uuid4())),
    )

    assert missing in result
    assert runner.calls == []


# --- passthrough / context --------------------------------------------------


async def test_task_only_call_runs_with_no_documents(
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    runner = SpyRunner()
    tool = _make_tool(tool_session_factory, runner)

    await _coro(tool)(
        agent_type="general-purpose",
        task="Do a self-contained thing.",
        runtime=_runtime(project_id=str(uuid.uuid4())),
    )

    (call,) = runner.calls
    assert call["documents"] == []
    assert call["task"] == "Do a self-contained thing."


async def test_runtime_config_and_canary_are_passed_through(
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    runner = SpyRunner()
    tool = _make_tool(tool_session_factory, runner)
    config = {"tags": ["main-graph"], "callbacks": []}

    await _coro(tool)(
        agent_type="judge",
        task="task",
        runtime=_runtime(
            project_id=str(uuid.uuid4()), canary_token="canary-42", config=config
        ),
    )

    (call,) = runner.calls
    # The Runner needs the main-graph config (tags/callbacks) and the canary
    # for its in-cycle guard checks — both come from ``runtime``.
    assert call["config"] == config
    assert call["canary_token"] == "canary-42"


async def test_missing_agent_context_raises(
    tool_session_factory: Callable[[], AsyncSession],
) -> None:
    runner = SpyRunner()
    tool = _make_tool(tool_session_factory, runner)

    with pytest.raises(RuntimeError, match="AgentContext"):
        await _coro(tool)(
            agent_type="judge",
            task="task",
            runtime=_runtime(project_id="x", with_context=False),
        )
