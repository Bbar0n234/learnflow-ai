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

Since the ``LLM_DEFENSE_ENABLED`` kill-switch, the review-event pair
(``final_output_review_started`` / ``..._complete``) is emitted only while the
enforcer reports ``active`` — the single public signal the runner reads. Both
states are covered here: with defense on the pair frames the end-of-stream
check, with defense off it disappears while the rest of the stream (and the
check itself) is unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
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
from app.agent.runtime_security import RuntimeSecurityEnforcer, SecurityOutcome
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
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
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from learnflow_testing.fakes import StubGuard
from structlog.testing import capture_logs
from tests.agent.conftest import (
    RaisingFakeChatModel,
    RecordingPromptProvider,
    streaming_tool_fake,
    tool_binding_fake,
)


@tool
def echo(text: str) -> str:
    """Echo the given text back (drives the ReAct loop in runner tests)."""
    return f"echoed: {text}"


class _InjectionEnforcer:
    """Stub enforcer: reports an INJECTION verdict on user input, no DB effects."""

    active = True

    async def check_user_input(self, **kwargs: Any) -> GuardResult:
        return GuardResult(
            verdict=Verdict.INJECTION,
            checkpoint=Checkpoint.USER_INPUT,
            direction=Direction.INBOUND,
            detection_layer=None,
        )


class _StagedEnforcer:
    """Stub enforcer: user input passes; emits a ``SecurityOutcome`` at one of the
    later runtime checkpoints (mid-stream / final-output / post-stream in-graph).

    Models the enforcer's contract — each ``check_*`` performs its side effects
    internally and returns an outcome when the turn must be blocked — without the
    real guard/DB machinery, so the runner's own branch (emit ``security_block``
    and stop) is exercised in isolation.
    """

    def __init__(
        self,
        *,
        mid: SecurityOutcome | None = None,
        final: SecurityOutcome | None = None,
        in_graph: SecurityOutcome | None = None,
        active: bool = True,
    ) -> None:
        self._mid = mid
        self._final = final
        self._in_graph = in_graph
        self.active = active

    async def check_user_input(self, **kwargs: Any) -> GuardResult | None:
        return None

    async def check_mid_stream(self, **kwargs: Any) -> SecurityOutcome | None:
        return self._mid

    async def check_final_output(self, **kwargs: Any) -> SecurityOutcome | None:
        return self._final

    async def inspect_in_graph(self, **kwargs: Any) -> SecurityOutcome | None:
        return self._in_graph


def _outcome(
    reason: str, *, checkpoint: Checkpoint = Checkpoint.FINAL_OUTPUT
) -> SecurityOutcome:
    return SecurityOutcome(
        reason=reason,
        result=GuardResult(
            verdict=Verdict.INJECTION,
            checkpoint=checkpoint,
            direction=Direction.OUTBOUND,
            detection_layer=DetectionLayer.UNICODE,
        ),
    )


def _make_runner(
    model: Any,
    *,
    enforcer: Any | None = None,
    tools: list[Any] | None = None,
    guard: Any | None = None,
) -> LangGraphAgentRunner:
    """Build a runner; ``guard`` decides whether the real enforcer is active.

    ``guard=None`` (default) is the ``LLM_DEFENSE_ENABLED=false`` shape — the
    composition root hands ``None`` down and every ``check_*`` short-circuits.
    Passing a ``StubGuard`` models defense-on without a live classifier.
    """
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
        global_tools=tools or [],
        skills_index="",
        checkpointer=checkpointer,
        store=store,
        prompt_provider=prompt_provider,
        security_guard=None,
        model_factory=lambda s, mc: model,
    )
    history = CheckpointHistory(checkpointer, security_messages)
    real_enforcer = RuntimeSecurityEnforcer(
        guard=guard, security_messages=security_messages, history=history
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
    # Defense on (a guard was built): the review pair frames the end-of-stream
    # check the user is told about.
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="Hello world")]),
        guard=StubGuard(Verdict.CLEAN),
    )

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "Hello world"
    assert "final_output_review_started" in types
    assert "final_output_review_complete" in types
    assert "error" not in types
    assert "security_block" not in types


@pytest.mark.integration
async def test_stream_defense_off_omits_the_review_events_but_keeps_the_text() -> None:
    # LLM_DEFENSE_ENABLED=false reaches the runner as a guard-less enforcer:
    # the user must not be told "checking your answer" when nothing is checked,
    # while the rest of the stream contract is untouched.
    runner = _make_runner(tool_binding_fake([AIMessage(content="Hello world")]))

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "Hello world"
    assert "final_output_review_started" not in types
    assert "final_output_review_complete" not in types
    assert "error" not in types
    assert "security_block" not in types


@pytest.mark.integration
async def test_final_output_check_runs_even_when_review_events_are_muted() -> None:
    # The runner mutes the *events* on inactive defense but keeps calling
    # ``check_final_output`` unconditionally (it short-circuits on its own).
    # Observable proof: an inactive enforcer that still returns an outcome
    # blocks the turn — so the call was made, without any review event.
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="Hello world")]),
        enforcer=_StagedEnforcer(final=_outcome("llm_classifier"), active=False),
    )

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    assert "security_block" in types
    assert "final_output_review_started" not in types
    assert "final_output_review_complete" not in types


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


# --- negative: client disconnect mid-stream -----------------------------------


@pytest.mark.integration
async def test_client_disconnect_logs_client_disconnected_status() -> None:
    # Closing the stream generator mid-run is what the ASGI layer does on a
    # client disconnect (GeneratorExit at the suspended yield). The run must
    # report status="client_disconnected" — not the misleading "ok" — and log
    # "agent completed" exactly once.
    runner = _make_runner(tool_binding_fake([AIMessage(content="Hello world")]))
    stream = runner.stream(content="hi", **_ids())
    assert isinstance(stream, AsyncGenerator)  # narrows to expose aclose()

    with capture_logs() as logs:
        await anext(stream)
        await stream.aclose()

    completed = [e for e in logs if e["event"] == "agent completed"]
    assert [e["status"] for e in completed] == ["client_disconnected"]


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


# --- negative: mid-stream security block (tail check) ------------------------


@pytest.mark.integration
async def test_mid_stream_injection_emits_security_block_and_no_text() -> None:
    # The enforcer flags the streamed tail on the first chunk: the runner must
    # emit ``security_block`` (carrying the outcome's reason) and stop before any
    # ``text_chunk`` reaches the client.
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="leaked secret")]),
        enforcer=_StagedEnforcer(mid=_outcome("unicode")),
    )

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    assert "security_block" in types
    assert "text_chunk" not in types
    assert "final_output_review_complete" not in types
    block = next(e for e in events if e.type == "security_block")
    assert block.data["reason"] == "unicode"


# --- negative: end-of-stream final-output security block ---------------------


@pytest.mark.integration
async def test_final_output_injection_blocks_after_text_streamed() -> None:
    # Mid-stream passes, so text streams and review starts; the end-of-stream
    # classifier then flags it: ``security_block`` fires and the review never
    # completes.
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="Hello world")]),
        enforcer=_StagedEnforcer(final=_outcome("llm_classifier")),
    )

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "Hello world"
    assert "final_output_review_started" in types
    assert "final_output_review_complete" not in types
    block = next(e for e in events if e.type == "security_block")
    assert block.data["reason"] == "llm_classifier"
    # security_block is terminal: nothing emitted after it.
    assert types[-1] in {"security_block", "trace_id"}


# --- negative: post-stream in-graph redaction inspection ---------------------


@pytest.mark.integration
async def test_in_graph_redaction_emits_security_block_after_review_complete() -> None:
    # Both stream-time checks pass (review completes), but a TOOL_* redaction was
    # recorded in-graph: the post-stream inspection surfaces it as security_block.
    runner = _make_runner(
        tool_binding_fake([AIMessage(content="Hello world")]),
        enforcer=_StagedEnforcer(
            in_graph=_outcome("fragment", checkpoint=Checkpoint.TOOL_RESULT)
        ),
    )

    events = await _collect(runner, content="hi", **_ids())

    types = [e.type for e in events]
    assert "final_output_review_complete" in types
    block = next(e for e in events if e.type == "security_block")
    assert block.data["reason"] == "fragment"
    # Block comes after the (clean) review completed.
    assert types.index("security_block") > types.index("final_output_review_complete")


# --- tool lifecycle: real astream drives tool_start / tool_end ---------------


@pytest.mark.integration
async def test_tool_call_emits_tool_start_and_tool_end_via_astream() -> None:
    # A real ReAct turn through the runner's graph: the model issues a tool call,
    # the tools node runs it, the model answers. The runner must surface the
    # graph ``updates`` as tool_start/tool_end (mapper wired through astream).
    model = streaming_tool_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    runner = _make_runner(model, tools=[echo])

    events = await _collect(runner, content="use the tool", **_ids())

    by_type = {e.type: e for e in events}
    assert "tool_start" in by_type
    assert "tool_end" in by_type
    assert by_type["tool_start"].data == {"tool": "echo", "call_id": "c1"}
    assert by_type["tool_end"].data == {"tool": "echo", "call_id": "c1"}
    # tool_start precedes tool_end; final answer still streamed as text.
    types = [e.type for e in events]
    assert types.index("tool_start") < types.index("tool_end")
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "done"


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
async def test_pending_cancel_is_scoped_to_its_thread() -> None:
    # Cancelling an idle thread registers a *pending* cancel (returns True) that
    # must fire only for that thread. A subsequent stream on a *different* thread
    # is unaffected — guards against a global/boolean cancel flag regression.
    runner = _make_runner(tool_binding_fake([AIMessage(content="Hello world")]))

    assert await runner.cancel(thread_id=uuid.uuid4()) is True

    events = await _collect(runner, content="hi", **_ids())
    types = [e.type for e in events]
    text = "".join(e.data["content"] for e in events if e.type == "text_chunk")
    assert text == "Hello world"
    assert "error" not in types
