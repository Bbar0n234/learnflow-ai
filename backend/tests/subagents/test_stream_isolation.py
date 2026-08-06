"""Subagent token isolation in the main stream loop (feat-011, T1.4).

Contract (design-brief § "Стриминг: изоляция токенов субагента"): LLM tokens
produced *inside* a subagent run carry the ``subagent`` tag and must be dropped
by ``LangGraphAgentRunner``'s ``stream_mode="messages"`` branch — before they
reach ``full_response`` or the chat — while the main agent's own tokens stream
normally and the ``tool_result`` indication for ``run_subagent``
(written by the tools node onto ``stream_mode="custom"``) still flows.

We drive the *real* ``LangGraphAgentRunner`` with a fake graph that scripts a
mixed chunk sequence (tagged + untagged messages, plus the node's own custom
writes — the channel the token filter must not swallow along with them). The guard is
off (real enforcer, ``guard=None`` -> every checkpoint no-ops), so the observable
contract is just the emitted ``StreamEvent`` sequence. This exercises the filter
code directly, independent of whether LangGraph's own ``subgraphs=False`` default
would also hide the chunks.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import ResolvedModelConfig, load_error_messages
from app.agent.runner import LangGraphAgentRunner
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.types import SecurityMessages
from app.agent.stream_events import tool_result_envelope
from app.agent.subagents import SUBAGENT_TAG
from app.agent.tracing import AgentRunTracer
from app.services.agent_runner import StreamEvent
from langchain_core.messages import AIMessageChunk, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

pytestmark = pytest.mark.unit


class _FakeGraph:
    """Yields a scripted ``(mode, data)`` sequence from ``astream``.

    Reproduces what the real main graph emits while a ``run_subagent`` tool
    runs: the main agent's own message chunks (no tag), the subagent's chunks
    (``subagent`` tag, via callbacks), and the ``updates`` for the tool.
    """

    def __init__(self, events: list[tuple[str, Any]]) -> None:
        self._events = events

    async def astream(
        self,
        _input: Any,
        _config: Any = None,
        *,
        stream_mode: Any = None,
        context: Any = None,
    ) -> AsyncIterator[tuple[str, Any]]:
        for event in self._events:
            yield event


class _FakeFactory:
    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph

    def build(self, _model_config: Any, *, extra_tools: Any = None) -> _FakeGraph:
        return self._graph


def _chunk(content: str, *, tags: list[str] | None = None) -> tuple[str, Any]:
    metadata: dict[str, Any] = {}
    if tags is not None:
        metadata["tags"] = tags
    return (
        "messages",
        (AIMessageChunk(content=content, id=str(uuid.uuid4())), metadata),
    )


def _make_runner(graph: _FakeGraph) -> LangGraphAgentRunner:
    security_messages = SecurityMessages()
    history = CheckpointHistory(InMemorySaver(), security_messages)
    enforcer = RuntimeSecurityEnforcer(
        guard=None, security_messages=security_messages, history=history
    )
    tracer = AgentRunTracer(enabled=False, security_messages=security_messages)
    return LangGraphAgentRunner(
        _FakeFactory(graph),  # type: ignore[arg-type]
        _DummyResolver(),  # type: ignore[arg-type]
        tracer,
        enforcer,
        history,
        load_error_messages(),
    )


class _DummyResolver:
    """Unused: a ``model_config`` is passed to ``stream`` so ``resolve`` is skipped."""


async def _collect(runner: LangGraphAgentRunner) -> list[StreamEvent]:
    return [
        event
        async for event in runner.stream(
            thread_id=uuid.uuid4(),
            content="hi",
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model_config=ResolvedModelConfig(
                model="fake", extra_body=None, source="config"
            ),
        )
    ]


async def test_subagent_tagged_tokens_are_dropped_from_the_chat() -> None:
    graph = _FakeGraph(
        [
            _chunk("Hello ", tags=[]),
            _chunk("LEAKED_A", tags=[SUBAGENT_TAG]),
            _chunk("LEAKED_B", tags=[SUBAGENT_TAG, "seq:step:3"]),
            _chunk("world", tags=[]),
        ]
    )
    runner = _make_runner(graph)

    events = await _collect(runner)

    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    # Only the main agent's untagged tokens reach the chat / full_response.
    assert text == "Hello world"
    assert "LEAKED_A" not in text and "LEAKED_B" not in text


async def test_tool_result_still_flows_while_tokens_are_filtered() -> None:
    graph = _FakeGraph(
        [
            _chunk("LEAKED", tags=[SUBAGENT_TAG]),
            (
                "custom",
                tool_result_envelope(
                    ToolMessage(
                        content="verdict",
                        name="run_subagent",
                        tool_call_id="c1",
                    )
                ),
            ),
            _chunk("final answer", tags=[]),
        ]
    )
    runner = _make_runner(graph)

    events = await _collect(runner)

    types = [e.type for e in events]
    # The subagent-work indication survives the token filter.
    assert "tool_result" in types
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "final answer"
    assert "LEAKED" not in text
