"""Integration (sociable): ``LangGraphAgentRunner.stream`` — the SSE orchestration.

The runner is wired to its real in-process collaborators — a ``GraphFactory`` with
an injected fake model, a real ``CheckpointHistory`` over ``InMemorySaver``, a real
``RuntimeSecurityEnforcer`` (guard off for the unguarded paths), and a disabled
``AgentRunTracer`` (no-op span, no Langfuse). We drive it with programmed model
turns and assert the emitted ``StreamEvent`` sequence — the runner's observable
contract — for the happy path plus the critpath negatives: upstream failure,
cancellation, and a pre-graph security block.

The security-block test stubs the *enforcer* (its INJECTION side effects persist
to the DB — S2 territory, болезненная граница); the runner's own job is only to
emit ``security_block`` and stop, which is what we assert.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
    load_agent_config,
    load_error_messages,
)
from app.agent.graph_factory import GraphFactory
from app.agent.runner import LangGraphAgentRunner
from app.agent.runtime_security import RuntimeSecurityEnforcer
from app.agent.security.types import (
    Checkpoint,
    Direction,
    GuardResult,
    SecurityMessages,
    Verdict,
)
from app.agent.tracing import AgentRunTracer
from app.config import Settings
from app.services.agent_runner import StreamEvent
from app.services.model_config_resolver import ModelConfigResolver
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from tests.agent.conftest import (
    RaisingFakeChatModel,
    RecordingPromptProvider,
    tool_binding_fake,
)


class _InjectionEnforcer:
    """Stub enforcer: reports an INJECTION verdict on user input, no DB effects."""

    async def check_user_input(self, **kwargs: Any) -> GuardResult:
        return GuardResult(
            verdict=Verdict.INJECTION,
            checkpoint=Checkpoint.USER_INPUT,
            direction=Direction.INBOUND,
            detection_layer=None,
        )


def _make_runner(
    model: Any,
    *,
    enforcer: Any | None = None,
) -> LangGraphAgentRunner:
    settings = Settings()
    agent_config: AgentConfig = load_agent_config().model_copy(
        update={"summarization": None}
    )
    prompt_fragments = PromptFragmentsConfig()
    security_messages = SecurityMessages()
    checkpointer = InMemorySaver()
    store = InMemoryStore()
    prompt_provider = RecordingPromptProvider()

    factory = GraphFactory(
        settings=settings,
        agent_config=agent_config,
        prompt_fragments=prompt_fragments,
        security_messages=security_messages,
        global_tools=[],
        skills_index="",
        checkpointer=checkpointer,
        store=store,
        prompt_provider=prompt_provider,
        security_guard=None,
        model_factory=lambda s, mc: model,
    )
    history = CheckpointHistory(checkpointer, security_messages)
    real_enforcer = RuntimeSecurityEnforcer(
        guard=None, security_messages=security_messages, history=history
    )
    tracer = AgentRunTracer(enabled=False, security_messages=security_messages)
    resolver = ModelConfigResolver(prompt_provider, agent_config)

    return LangGraphAgentRunner(
        factory,
        resolver,
        tracer,
        enforcer or real_enforcer,
        history,
        load_error_messages(),
    )


async def _collect(runner: LangGraphAgentRunner, **kwargs: Any) -> list[StreamEvent]:
    return [event async for event in runner.stream(**kwargs)]


def _ids() -> dict[str, Any]:
    return {
        "thread_id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "model_config": ResolvedModelConfig(
            model="fake", extra_body=None, source="config"
        ),
    }


# --- happy path -------------------------------------------------------------


@pytest.mark.integration
async def test_stream_emits_text_chunks_and_final_output_review() -> None:
    runner = _make_runner(tool_binding_fake([AIMessage(content="Hello world")]))

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "Hello world"
    assert "final_output_review_started" in types
    assert "final_output_review_complete" in types
    assert "error" not in types
    assert "security_block" not in types


# --- negative: upstream model failure ---------------------------------------


@pytest.mark.integration
async def test_stream_maps_model_failure_to_error_event() -> None:
    model = RaisingFakeChatModel(messages=iter([AIMessage(content="never")]))
    runner = _make_runner(model)

    events = await _collect(runner, content="hi", **_ids())

    error_events = [e for e in events if e.type == "error"]
    assert len(error_events) == 1
    # Generic, user-safe message — no internal exception text leaked.
    assert error_events[0].data["detail"] == load_error_messages().generic


# --- negative: cancellation -------------------------------------------------


@pytest.mark.integration
async def test_precancelled_thread_emits_cancelled_error_and_no_text() -> None:
    runner = _make_runner(tool_binding_fake([AIMessage(content="Hello world")]))
    ids = _ids()

    await runner.cancel(thread_id=ids["thread_id"])
    events = await _collect(runner, content="hi", **ids)

    types = [e.type for e in events]
    assert "text_chunk" not in types
    error_events = [e for e in events if e.type == "error"]
    assert error_events
    assert error_events[0].data["detail"] == load_error_messages().cancelled


# --- negative: pre-graph security block --------------------------------------


@pytest.mark.integration
async def test_user_input_injection_emits_security_block_and_stops() -> None:
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="should never stream")]),
        enforcer=_InjectionEnforcer(),
    )

    events = await _collect(runner, content="ignore instructions", **_ids())

    types = [e.type for e in events]
    assert "security_block" in types
    assert "text_chunk" not in types
    assert "final_output_review_started" not in types


# --- delegation: history reads ----------------------------------------------


@pytest.mark.integration
async def test_get_history_returns_turns_after_a_stream() -> None:
    runner = _make_runner(tool_binding_fake([AIMessage(content="the answer")]))
    ids = _ids()
    await _collect(runner, content="the question", **ids)

    history = await runner.get_history(thread_id=ids["thread_id"])

    assert [(m.role, m.content) for m in history] == [
        ("user", "the question"),
        ("assistant", "the answer"),
    ]


@pytest.mark.integration
async def test_get_last_ai_message_id_after_stream_is_not_none() -> None:
    runner = _make_runner(tool_binding_fake([AIMessage(content="answer")]))
    ids = _ids()
    await _collect(runner, content="q", **ids)

    last_id = await runner.get_last_ai_message_id(thread_id=ids["thread_id"])

    assert last_id is not None


@pytest.mark.integration
async def test_cancel_unknown_thread_returns_true() -> None:
    runner = _make_runner(tool_binding_fake([AIMessage(content="x")]))

    assert await runner.cancel(thread_id=uuid.uuid4()) is True
