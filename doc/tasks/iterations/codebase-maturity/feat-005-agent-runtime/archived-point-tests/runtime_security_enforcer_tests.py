"""feat-005: RuntimeSecurityEnforcer — runtime guard checkpoints (concern 1).

Critical path. Verifies verdict→outcome mapping, that blocking checkpoints run
their side effects (persist / redact via graph.aupdate_state), and that the
guard is invoked with the right checkpoint + flags. DB marking is covered by the
manual smoke cases (session_factory=None here → mark is a safe no-op).
"""

import asyncio
import uuid
from types import SimpleNamespace

from app.agent.checkpoint_history import CheckpointHistory
from app.agent.runtime_security import RuntimeSecurityEnforcer, SecurityOutcome
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    GuardResult,
    SecurityMessages,
    Verdict,
    direction_of,
)
from langchain_core.messages import AIMessage, HumanMessage

_MESSAGES = SecurityMessages()
_TID = uuid.uuid4()
_CONFIG = {"configurable": {"thread_id": str(_TID)}}


class _FakeGuard:
    def __init__(self, verdict: Verdict, layer: DetectionLayer | None = None) -> None:
        self._verdict = verdict
        self._layer = layer
        self.calls: list[dict] = []

    async def check(
        self,
        content,
        checkpoint,
        *,
        history=None,
        canary_token=None,
        skip_classifier=False,
        observe=True,
        trace_ctx=None,
    ) -> GuardResult:
        self.calls.append(
            {
                "checkpoint": checkpoint,
                "skip_classifier": skip_classifier,
                "observe": observe,
            }
        )
        return GuardResult(
            verdict=self._verdict,
            checkpoint=checkpoint,
            direction=direction_of(checkpoint),
            detection_layer=self._layer,
        )


class _FakeGraph:
    def __init__(self) -> None:
        self.updates: list = []

    async def aupdate_state(self, config, update, as_node=None) -> None:
        self.updates.append((config, update, as_node))


class _FakeCheckpointer:
    def __init__(self, messages: list | None) -> None:
        self._messages = messages

    async def aget_tuple(self, config):
        if self._messages is None:
            return None
        return SimpleNamespace(
            checkpoint={"channel_values": {"messages": self._messages}}
        )


def _enforcer(
    guard: _FakeGuard | None, messages: list | None = None
) -> RuntimeSecurityEnforcer:
    history = CheckpointHistory(_FakeCheckpointer(messages), _MESSAGES)
    return RuntimeSecurityEnforcer(
        guard=guard,
        security_messages=_MESSAGES,
        history=history,
        session_factory=None,
    )


# --- block_reason ---


def test_block_reason_uses_layer_then_fallback() -> None:
    with_layer = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=direction_of(Checkpoint.USER_INPUT),
        detection_layer=DetectionLayer.CANARY,
    )
    without = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=direction_of(Checkpoint.USER_INPUT),
        detection_layer=None,
    )
    assert RuntimeSecurityEnforcer.block_reason(with_layer) == "canary"
    assert RuntimeSecurityEnforcer.block_reason(without) == "prompt_injection"


# --- check_user_input ---


def test_user_input_none_when_guard_off() -> None:
    assert (
        asyncio.run(
            _enforcer(None).check_user_input(
                thread_id=_TID, content="hi", canary_token="", graph=_FakeGraph()
            )
        )
        is None
    )


def test_user_input_injection_persists_block() -> None:
    graph = _FakeGraph()
    result = asyncio.run(
        _enforcer(_FakeGuard(Verdict.INJECTION)).check_user_input(
            thread_id=_TID, content="evil", canary_token="", graph=graph
        )
    )
    assert result is not None and result.verdict == Verdict.INJECTION
    # Persisted the blocked human + placeholder turn with correct content/flags.
    assert len(graph.updates) == 1
    _config, update, as_node = graph.updates[0]
    assert as_node == "agent"
    human, placeholder = update["messages"]
    assert human.content == "evil"
    assert placeholder.content == _MESSAGES.redacted_user_facing
    assert placeholder.additional_kwargs["security_redacted"] is True
    # No detection layer on this guard verdict → falls back to checkpoint value.
    assert (
        placeholder.additional_kwargs["original_detection_layer"]
        == Checkpoint.USER_INPUT.value
    )


def test_user_input_clean_no_side_effects() -> None:
    graph = _FakeGraph()
    result = asyncio.run(
        _enforcer(_FakeGuard(Verdict.CLEAN)).check_user_input(
            thread_id=_TID, content="hi", canary_token="", graph=graph
        )
    )
    assert result is not None and result.verdict == Verdict.CLEAN
    assert graph.updates == []


def test_user_input_suspicious_proceeds() -> None:
    graph = _FakeGraph()
    result = asyncio.run(
        _enforcer(_FakeGuard(Verdict.SUSPICIOUS)).check_user_input(
            thread_id=_TID, content="hmm", canary_token="", graph=graph
        )
    )
    assert result is not None and result.verdict == Verdict.SUSPICIOUS
    assert graph.updates == []


# --- check_mid_stream ---


def test_mid_stream_injection_redacts() -> None:
    graph = _FakeGraph()
    guard = _FakeGuard(Verdict.INJECTION, DetectionLayer.CANARY)
    outcome = asyncio.run(
        _enforcer(guard).check_mid_stream(
            thread_id=_TID,
            full_response="full",
            tail="tail",
            canary_token="",
            graph=graph,
            config=_CONFIG,
            last_message_id="a1",
        )
    )
    assert isinstance(outcome, SecurityOutcome)
    assert outcome.reason == "canary"
    assert len(graph.updates) == 1
    _config, update, _node = graph.updates[0]
    (redacted,) = update["messages"]
    assert redacted.id == "a1"
    assert redacted.content == _MESSAGES.redacted_user_facing
    assert redacted.additional_kwargs["security_redacted"] is True
    assert redacted.additional_kwargs["original_detection_layer"] == "canary"
    # Deterministic tail check: classifier skipped, observation suppressed.
    assert guard.calls[0]["skip_classifier"] is True
    assert guard.calls[0]["observe"] is False
    assert guard.calls[0]["checkpoint"] == Checkpoint.FINAL_OUTPUT


def test_mid_stream_clean_returns_none() -> None:
    graph = _FakeGraph()
    outcome = asyncio.run(
        _enforcer(_FakeGuard(Verdict.CLEAN)).check_mid_stream(
            thread_id=_TID,
            full_response="full",
            tail="tail",
            canary_token="",
            graph=graph,
            config=_CONFIG,
            last_message_id="a1",
        )
    )
    assert outcome is None
    assert graph.updates == []


def test_mid_stream_injection_without_layer_falls_back_reason() -> None:
    # No detection layer → reason falls back to "final_output".
    outcome = asyncio.run(
        _enforcer(_FakeGuard(Verdict.INJECTION)).check_mid_stream(
            thread_id=_TID,
            full_response="full",
            tail="tail",
            canary_token="",
            graph=_FakeGraph(),
            config=_CONFIG,
            last_message_id="a1",
        )
    )
    assert outcome is not None
    assert outcome.reason == "final_output"


# --- check_final_output ---


def test_final_output_injection_redacts() -> None:
    graph = _FakeGraph()
    guard = _FakeGuard(Verdict.INJECTION, DetectionLayer.LLM_CLASSIFIER)
    outcome = asyncio.run(
        _enforcer(guard).check_final_output(
            thread_id=_TID,
            full_response="leak",
            canary_token="",
            graph=graph,
            config=_CONFIG,
            last_message_id="a1",
        )
    )
    assert isinstance(outcome, SecurityOutcome)
    assert len(graph.updates) == 1
    _config, update, _node = graph.updates[0]
    (redacted,) = update["messages"]
    assert redacted.id == "a1"
    assert redacted.content == _MESSAGES.redacted_user_facing
    assert redacted.additional_kwargs["security_redacted"] is True
    assert (
        redacted.additional_kwargs["original_detection_layer"]
        == DetectionLayer.LLM_CLASSIFIER.value
    )
    # End-of-stream runs the full classifier.
    assert guard.calls[0]["skip_classifier"] is False
    assert guard.calls[0]["checkpoint"] == Checkpoint.FINAL_OUTPUT


def test_final_output_clean_returns_none() -> None:
    graph = _FakeGraph()
    outcome = asyncio.run(
        _enforcer(_FakeGuard(Verdict.CLEAN)).check_final_output(
            thread_id=_TID,
            full_response="ok",
            canary_token="",
            graph=graph,
            config=_CONFIG,
            last_message_id="a1",
        )
    )
    assert outcome is None
    assert graph.updates == []


# --- inspect_in_graph ---


def test_inspect_in_graph_detects_redaction() -> None:

    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="",
            id="a1",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
            },
        ),
    ]
    outcome = asyncio.run(
        _enforcer(_FakeGuard(Verdict.CLEAN), messages=messages).inspect_in_graph(
            thread_id=_TID
        )
    )
    assert isinstance(outcome, SecurityOutcome)
    assert outcome.result.checkpoint == Checkpoint.TOOL_CALL_ARG
    assert outcome.result.verdict == Verdict.INJECTION
    assert outcome.reason == DetectionLayer.LLM_CLASSIFIER.value


def test_inspect_in_graph_clean_returns_none() -> None:

    messages = [AIMessage(content="answer", id="a1")]
    outcome = asyncio.run(
        _enforcer(_FakeGuard(Verdict.CLEAN), messages=messages).inspect_in_graph(
            thread_id=_TID
        )
    )
    assert outcome is None
