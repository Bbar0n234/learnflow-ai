"""Subagent steps on the parent stream (design-brief § «Вложенность субагента»).

A subagent runs its own compiled graph through ``ainvoke``, so nothing it does
is visible to the parent stream by itself: ``get_stream_writer()`` inside that
nested run resolves to a writer nobody reads. The contract therefore hangs on
an explicit hand-over — the ``run_subagent`` tool captures the *main* graph's
writer and its own ``call_id`` and passes both down, and every tool the
subagent executes is wrapped so its work is reported with those four familiar
event types plus ``parent_call_id``.

Everything here is about events that go missing *silently*: if the hand-over
breaks, nothing raises and no assertion elsewhere turns red — the activity feed
just shows an opaque subagent row with nothing inside it. So these cases pin the
whole reported sequence, the failure branch, and the fact that the contextual
attribution is cleared afterwards instead of sticking to whatever runs next.

The LLM seam is faked the same way ``test_runner.py`` does it
(``create_llm_from_config`` monkeypatched); the subagent graph, its ``ToolNode``
and the wrapper are all real.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from app.agent.agent_events import emit_agent_event
from app.agent.config import (
    AgentConfig,
    ContextConfig,
    ImageConfig,
    LLMConfig,
    SubagentsConfig,
    SubagentSpec,
    TitleConfig,
)
from app.agent.graph import AgentContext
from app.agent.subagents.graph import build_subagent_graph
from app.agent.subagents.runner import SubagentRunner
from app.agent.tools.subagents import make_run_subagent_tool
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, tool
from langgraph.prebuilt import ToolRuntime

from tests.subagents.conftest import CapturingModel, RecordingPromptProvider

pytestmark = pytest.mark.unit


@tool
def note(text: str) -> str:
    """Record a note (stands in for a KS/memory tool the subagent may use).

    Reports its domain write through ``emit_agent_event`` exactly like the real
    ones — with no idea whether it runs in the main graph or under a subagent.
    """
    emit_agent_event("memory_write", {"key": text})
    return f"noted: {text}"


@tool
def explode(text: str) -> str:
    """Always raises — the failure branch of a subagent tool call."""
    raise RuntimeError(f"tool blew up on {text}")


class _RecordingWriter:
    """The main graph's stream writer as the subagent side sees it."""

    def __init__(self) -> None:
        self.written: list[dict[str, Any]] = []

    def __call__(self, item: Any) -> None:
        self.written.append(item)

    @property
    def types(self) -> list[str]:
        return [item["type"] for item in self.written]

    def of_type(self, type_: str) -> dict[str, Any]:
        return next(item for item in self.written if item["type"] == type_)


def _config(tool_name: str) -> AgentConfig:
    """Minimal config whose single spec draws exactly the tool under test."""
    return AgentConfig(
        llm=LLMConfig(model="main"),
        context=ContextConfig(max_tokens=8000),
        image=ImageConfig(model="img"),
        title=TitleConfig(model="title"),
        subagents=SubagentsConfig(
            llm=LLMConfig(model="sub"),
            registry=[
                SubagentSpec(
                    name="judge",
                    description="d",
                    prompt="subagent-judge",
                    tools=[tool_name],
                )
            ],
        ),
    )


def _make_runner(
    monkeypatch: pytest.MonkeyPatch,
    model: Any,
    subagent_tool: Any,
    prompt_fragments: Any,
) -> SubagentRunner:
    monkeypatch.setattr(
        "app.agent.subagents.runner.create_llm_from_config",
        lambda _settings, _model_config: model,
    )
    return SubagentRunner(
        agent_config=_config(subagent_tool.name),
        prompt_fragments=prompt_fragments,
        prompt_provider=RecordingPromptProvider(),
        settings=cast(Any, object()),  # only forwarded to the faked model factory
        tool_pool={subagent_tool.name: subagent_tool},
    )


# --- the reported sequence ---------------------------------------------------


async def test_a_subagent_tool_call_is_reported_as_four_attributed_events(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # The nested row of the feed is built from exactly these four events, and
    # every one of them must name the parent call it belongs under — otherwise
    # the step renders as the main agent's own work.
    model = CapturingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "note", "args": {"text": "x"}, "id": "inner-1"}],
            ),
            AIMessage(content="verdict"),
        ]
    )
    runner = _make_runner(monkeypatch, model, note, prompt_fragments)
    writer = _RecordingWriter()

    result = await runner.run(
        "judge", "review this", stream_writer=writer, parent_call_id="outer-1"
    )

    assert result == "verdict"
    assert writer.types == [
        "tool_call_started",
        "tool_call_args",
        "memory_write",
        "tool_result",
    ]
    assert writer.of_type("tool_call_started")["data"] == {
        "call_id": "inner-1",
        "tool": "note",
        "parent_call_id": "outer-1",
    }
    assert writer.of_type("tool_call_args")["data"] == {
        "call_id": "inner-1",
        "args": '{"text": "x"}',
        "truncated": False,
        "parent_call_id": "outer-1",
    }
    assert writer.of_type("tool_result")["data"] == {
        "call_id": "inner-1",
        "tool": "note",
        "status": "success",
        "content": "noted: x",
        "truncated": False,
        "parent_call_id": "outer-1",
    }


async def test_a_domain_event_from_inside_the_subagent_reaches_the_parent_writer(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # The nested graph has a working ``get_stream_writer()`` of its own, whose
    # output nobody reads — so a domain tool's event only survives because the
    # handed-over writer takes priority over it.
    model = CapturingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "note", "args": {"text": "ru"}, "id": "inner-1"}],
            ),
            AIMessage(content="verdict"),
        ]
    )
    runner = _make_runner(monkeypatch, model, note, prompt_fragments)
    writer = _RecordingWriter()

    await runner.run("judge", "task", stream_writer=writer, parent_call_id="outer-1")

    assert writer.of_type("memory_write") == {
        "type": "memory_write",
        "payload": {"key": "ru"},
        "parent_call_id": "outer-1",
    }


async def test_a_failing_subagent_tool_is_reported_as_an_error_result(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # The wrapper must report the failure and still let it reach ``ToolNode``'s
    # error handling, so the subagent's own loop continues as it would without
    # any reporting attached.
    model = CapturingModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "explode", "args": {"text": "x"}, "id": "inner-1"}
                ],
            ),
            AIMessage(content="could not finish"),
        ]
    )
    runner = _make_runner(monkeypatch, model, explode, prompt_fragments)
    writer = _RecordingWriter()

    result = await runner.run(
        "judge", "task", stream_writer=writer, parent_call_id="outer-1"
    )

    assert result == "could not finish"
    reported = writer.of_type("tool_result")["data"]
    assert reported["status"] == "error"
    assert "tool blew up on x" in reported["content"]
    assert reported["parent_call_id"] == "outer-1"


async def test_no_events_are_reported_without_a_writer_to_report_to(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # ``SubagentRunner.run`` is also called outside any stream; the wrapping is
    # skipped there and the run behaves exactly as before.
    model = CapturingModel(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "note", "args": {"text": "x"}, "id": "inner-1"}],
            ),
            AIMessage(content="verdict"),
        ]
    )
    runner = _make_runner(monkeypatch, model, note, prompt_fragments)

    assert await runner.run("judge", "task") == "verdict"


# --- the attribution is scoped to one call ----------------------------------


async def _wrapped_tools(
    monkeypatch: pytest.MonkeyPatch,
    subagent_tool: Any,
    prompt_fragments: Any,
    writer: _RecordingWriter,
    *,
    parent_call_id: str,
) -> list[Any]:
    """Run a subagent and return the tools it actually executed with.

    The wrapping happens inside ``SubagentRunner.run`` and the wrapped tools go
    straight into the graph, so the only way to get hold of them is at the
    collaborator boundary the runner hands them over at (``build_subagent_graph``).
    Holding them lets the next cases invoke a subagent tool call *in the test's
    own context*, which is where the contextvar scoping is observable at all:
    under ``ToolNode`` every call runs in its own task with its own copy of the
    context, so nothing set (or left unset) inside it can be seen from outside.
    """
    captured: list[Any] = []
    real_build = build_subagent_graph

    def _spy(**kwargs: Any) -> Any:
        captured.extend(kwargs["tools"])
        return real_build(**kwargs)

    monkeypatch.setattr("app.agent.subagents.runner.build_subagent_graph", _spy)
    model = CapturingModel([AIMessage(content="verdict")])
    runner = _make_runner(monkeypatch, model, subagent_tool, prompt_fragments)
    await runner.run(
        "judge", "task", stream_writer=writer, parent_call_id=parent_call_id
    )
    writer.written.clear()  # the probing run itself made no tool calls
    return captured


def _call(tool_name: str, call_id: str, text: str) -> dict[str, Any]:
    return {
        "name": tool_name,
        "args": {"text": text},
        "id": call_id,
        "type": "tool_call",
    }


async def test_the_parent_attribution_does_not_outlive_one_tool_call(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # The leak this guards against is what happens *between* two calls: if the
    # writer and parent id stayed set after a call ended, the next domain event
    # of the run — the main agent's own work, a completely different row — would
    # be filed under this subagent and pushed into a writer that no longer
    # belongs to it. So the probe is an ordinary emission in between: it must
    # find no ambient subagent scope to attach itself to.
    writer = _RecordingWriter()
    tools = await _wrapped_tools(
        monkeypatch, note, prompt_fragments, writer, parent_call_id="outer-1"
    )

    await tools[0].ainvoke(_call("note", "inner-1", "first"))
    emit_agent_event("memory_write", {"key": "between the calls"})
    await tools[0].ainvoke(_call("note", "inner-2", "second"))

    assert writer.types == [
        "tool_call_started",
        "tool_call_args",
        "memory_write",
        "tool_result",
        "tool_call_started",
        "tool_call_args",
        "memory_write",
        "tool_result",
    ]
    # Only the two tool bodies reported a domain write; the one emitted between
    # them found no writer at all, so it never reached the stream.
    assert [item["payload"]["key"] for item in writer.written if "payload" in item] == [
        "first",
        "second",
    ]


async def test_the_parent_attribution_is_dropped_after_a_failing_tool_call(
    monkeypatch: pytest.MonkeyPatch, prompt_fragments: Any
) -> None:
    # Same guarantee on the failure path — the scope is unwound in ``finally``,
    # so an exception must not leave the attribution behind.
    writer = _RecordingWriter()
    tools = await _wrapped_tools(
        monkeypatch, explode, prompt_fragments, writer, parent_call_id="outer-1"
    )

    with pytest.raises(RuntimeError, match="tool blew up"):
        await tools[0].ainvoke(_call("explode", "inner-1", "x"))
    emit_agent_event("compaction", {})

    assert writer.types == ["tool_call_started", "tool_call_args", "tool_result"]


# --- the hand-over from the run_subagent tool -------------------------------


async def test_run_subagent_hands_its_own_writer_and_call_id_to_the_runner() -> None:
    # The one place where a live writer and this call's own id are both
    # available is the tool's own execution inside the main graph; if it fails
    # to pass them down, every nested event is silently dropped downstream.
    handed: dict[str, Any] = {}

    class _CapturingRunner:
        async def run(
            self,
            agent_type: str,
            task: str,
            documents: Any = None,
            *,
            config: Any = None,
            canary_token: str = "",
            stream_writer: Any = None,
            parent_call_id: str | None = None,
        ) -> str:
            handed["stream_writer"] = stream_writer
            handed["parent_call_id"] = parent_call_id
            return "verdict"

    writer = _RecordingWriter()
    subagent_tool = make_run_subagent_tool(
        cast(Any, None),  # session factory: only used for input_artifact_ids
        cast(Any, _CapturingRunner()),
        [],
    )
    runtime: ToolRuntime[AgentContext | None, dict[str, Any]] = ToolRuntime(
        state={},
        context=AgentContext(
            project_id=str(uuid.uuid4()), user_id="user-1", canary_token=""
        ),
        config=cast(Any, {}),
        stream_writer=writer,
        tool_call_id="outer-1",
        store=None,
    )

    coroutine = cast(Any, cast(StructuredTool, subagent_tool).coroutine)
    await coroutine(agent_type="judge", task="review", runtime=runtime)

    assert handed == {"stream_writer": writer, "parent_call_id": "outer-1"}
