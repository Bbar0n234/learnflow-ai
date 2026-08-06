"""Compaction as the user sees it: a fact in the feed, never its content.

Two guarantees meet in one run here (streaming.md § «Изоляция токенов: субагент
и суммаризатор»). The summarizer is an internal generation that happens in the
middle of the user's turn, so its tokens must never surface as the assistant's
answer — the isolation is done at the source, by detaching that call from the
parent run's callback chain, which is why nothing downstream filters it out and
a regression would silently paste the summary into the chat. And the *fact* of
compaction still has to be visible, as ``agent_event {kind: "compaction"}`` —
otherwise a long pause in the middle of a turn has no explanation on screen.

The run is real: a real graph with a real ``_reduce_context``, driven by the
real runner over ``astream``, with only the two models faked. Compaction is
provoked honestly — a context budget small enough that the second turn of the
thread crosses the threshold — rather than by calling the private helper.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import (
    AgentConfig,
    ContextConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
    load_agent_config,
    load_error_messages,
)
from app.agent.graph import build_graph, compile_graph
from app.agent.runner import LangGraphAgentRunner
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.types import SecurityMessages
from app.agent.tracing import AgentRunTracer
from app.services.agent_runner import StreamEvent
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from tests.agent.conftest import RecordingPromptProvider, tool_binding_fake

pytestmark = pytest.mark.integration

SUMMARY_TEXT = "SUMMARY OF THE EARLIER CONVERSATION"


class _PrebuiltFactory:
    """Graph factory handing out one already-compiled graph."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def build(self, _model_config: Any, *, extra_tools: Any = None) -> Any:
        return self._graph


class _DummyResolver:
    """Unused: ``model_config`` is passed to ``stream``."""


def _tiny_context_config() -> AgentConfig:
    """Real config with a context budget the second turn is bound to cross."""
    return load_agent_config().model_copy(
        update={
            "context": ContextConfig(
                max_tokens=10,
                compaction_threshold_ratio=0.5,
                recent_messages_to_keep=2,
            )
        }
    )


def _make_runner(answers: list[str], summarizer: Any) -> LangGraphAgentRunner:
    security_messages = SecurityMessages()
    checkpointer = InMemorySaver()
    builder = build_graph(
        model=tool_binding_fake([AIMessage(content=a) for a in answers]),
        tools=[],
        agent_config=_tiny_context_config(),
        prompt_fragments=PromptFragmentsConfig(),
        security_messages=security_messages,
        summarization_model=summarizer,
        prompt_provider=RecordingPromptProvider(),
    )
    graph = compile_graph(builder, checkpointer=checkpointer, store=InMemoryStore())
    history = CheckpointHistory(checkpointer, security_messages)
    return LangGraphAgentRunner(
        _PrebuiltFactory(graph),  # type: ignore[arg-type]
        _DummyResolver(),  # type: ignore[arg-type]
        AgentRunTracer(enabled=False, security_messages=security_messages),
        RuntimeSecurityEnforcer(
            guard=None, security_messages=security_messages, history=history
        ),
        history,
        load_error_messages(),
    )


async def _turn(
    runner: LangGraphAgentRunner, thread_id: uuid.UUID, content: str
) -> list[StreamEvent]:
    return [
        event
        async for event in runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model_config=ResolvedModelConfig(
                model="fake", extra_body=None, source="config"
            ),
        )
    ]


async def test_compaction_is_announced_without_leaking_the_summary() -> None:
    thread_id = uuid.uuid4()
    long_answer = "word " * 40  # pushes the thread over the tiny budget
    runner = _make_runner(
        [long_answer, "the second answer"],
        tool_binding_fake([AIMessage(content=SUMMARY_TEXT)]),
    )

    await _turn(runner, thread_id, "first question")
    second = await _turn(runner, thread_id, "second question " * 20)

    text = "".join(e.data["content"] for e in second if e.type == "text_chunk")
    assert text == "the second answer"
    assert SUMMARY_TEXT not in text
    compaction = [
        e for e in second if e.type == "agent_event" and e.data["kind"] == "compaction"
    ]
    assert [e.data for e in compaction] == [{"kind": "compaction", "payload": {}}]


async def test_a_turn_below_the_context_budget_reports_no_compaction() -> None:
    # The counterpart: the event means something happened, so it must not fire
    # on every turn.
    thread_id = uuid.uuid4()
    runner = _make_runner(
        ["short"], tool_binding_fake([AIMessage(content=SUMMARY_TEXT)])
    )

    events = await _turn(runner, thread_id, "hi")

    assert [e for e in events if e.type == "agent_event"] == []
