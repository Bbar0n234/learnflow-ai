"""Unit: ``AgentRunTracer`` / ``AgentRunSpan`` — fail-safe Langfuse wrapper.

Tracing must never break the agent stream: when disabled it yields a no-op span,
and every method swallows backend errors. We assert that observable contract —
disabled run yields a usable no-op handle, and span methods do not raise even
when the underlying observation throws — without asserting Langfuse internals.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    SecurityMessages,
    Verdict,
)
from app.agent.tracing import AgentRunSpan, AgentRunTracer


def _guard_result() -> GuardResult:
    return GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=Direction.INBOUND,
        detection_layer=DetectionLayer.CANARY,
    )


class _RaisingSpan:
    """Fake observation whose every method raises — exercises fail-safe paths."""

    trace_id = "trace-xyz"
    id = "obs-1"

    def update(self, **kwargs: Any) -> None:
        raise RuntimeError("langfuse down")

    def score_trace(self, **kwargs: Any) -> None:
        raise RuntimeError("langfuse down")


class _RecordingSpan:
    """Fake observation that records the exact kwargs of each call.

    Lets the positive contract assert the precise Langfuse payload the span emits
    (score name/value/type/comment, update output+metadata) — not just that it
    did not raise.
    """

    trace_id = "trace-xyz"
    id = "obs-1"

    def __init__(self) -> None:
        self.score_trace_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.update_calls.append(kwargs)

    def score_trace(self, **kwargs: Any) -> None:
        self.score_trace_calls.append(kwargs)


# --- positive contract: enabled span emits the expected Langfuse payload ----


@pytest.mark.unit
def test_score_emits_security_verdict_score_trace() -> None:
    rec = _RecordingSpan()
    span = AgentRunSpan(rec, None, enabled=True, security_messages=SecurityMessages())

    span.score(Verdict.SUSPICIOUS, DetectionLayer.UNICODE)

    assert rec.score_trace_calls == [
        {
            "name": "security_verdict",
            "value": "SUSPICIOUS",
            "data_type": "CATEGORICAL",
            "comment": "unicode",
        }
    ]
    assert rec.update_calls == []  # score does not touch the span output


@pytest.mark.unit
def test_score_without_detection_layer_sends_null_comment() -> None:
    rec = _RecordingSpan()
    span = AgentRunSpan(rec, None, enabled=True, security_messages=SecurityMessages())

    span.score(Verdict.CLEAN, None)

    assert rec.score_trace_calls[0]["value"] == "CLEAN"
    assert rec.score_trace_calls[0]["comment"] is None


@pytest.mark.unit
def test_finalize_blocked_scores_injection_and_updates_block_metadata() -> None:
    rec = _RecordingSpan()
    messages = SecurityMessages()
    span = AgentRunSpan(rec, None, enabled=True, security_messages=messages)

    span.finalize_blocked(_guard_result())

    assert rec.score_trace_calls == [
        {
            "name": "security_verdict",
            "value": "INJECTION",
            "data_type": "CATEGORICAL",
            "comment": "canary",
        }
    ]
    assert rec.update_calls == [
        {
            "output": messages.redacted_user_facing,
            "metadata": {
                "blocked": True,
                "checkpoint": "user_input",
                "detection_layer": "canary",
            },
            "level": "ERROR",
        }
    ]


@pytest.mark.unit
def test_set_output_updates_span_output() -> None:
    rec = _RecordingSpan()
    span = AgentRunSpan(rec, None, enabled=True, security_messages=SecurityMessages())

    span.set_output("final text")

    assert rec.update_calls == [{"output": "final text"}]


# --- disabled tracer --------------------------------------------------------


@pytest.mark.unit
def test_disabled_tracer_yields_noop_span_without_trace_id() -> None:
    tracer = AgentRunTracer(enabled=False, security_messages=SecurityMessages())

    with tracer.run(
        content="hi",
        user_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
    ) as span:
        assert span.trace_id is None
        assert span.callback_handler is None
        # No-op methods must not raise.
        span.score(Verdict.CLEAN, None)
        span.set_output("anything")
        span.finalize_blocked(_guard_result())


# --- fail-safe span methods -------------------------------------------------


@pytest.mark.unit
def test_score_suppresses_backend_error() -> None:
    span = AgentRunSpan(
        _RaisingSpan(), None, enabled=True, security_messages=SecurityMessages()
    )

    span.score(Verdict.SUSPICIOUS, DetectionLayer.UNICODE)  # must not raise


@pytest.mark.unit
def test_finalize_blocked_suppresses_backend_error() -> None:
    span = AgentRunSpan(
        _RaisingSpan(), None, enabled=True, security_messages=SecurityMessages()
    )

    span.finalize_blocked(_guard_result())  # must not raise


@pytest.mark.unit
def test_set_output_suppresses_backend_error() -> None:
    span = AgentRunSpan(
        _RaisingSpan(), None, enabled=True, security_messages=SecurityMessages()
    )

    span.set_output("final text")  # must not raise


@pytest.mark.unit
def test_record_mid_stream_hit_is_noop_when_disabled() -> None:
    # When disabled the method returns before touching the (optional) langfuse
    # import, so it is safe with a no-op span.
    span = AgentRunSpan(
        _RaisingSpan(), None, enabled=False, security_messages=SecurityMessages()
    )

    span.record_mid_stream_hit(
        thread_id=uuid.uuid4(),
        full_response="resp",
        tail="ail",
        result=_guard_result(),
        chunks_processed=3,
    )  # must not raise and must not call langfuse


@pytest.mark.unit
def test_trace_id_proxies_underlying_span() -> None:
    span = AgentRunSpan(
        _RaisingSpan(), "handler", enabled=True, security_messages=SecurityMessages()
    )

    assert span.trace_id == "trace-xyz"
    assert span.callback_handler == "handler"
