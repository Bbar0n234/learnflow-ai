"""feat-005: AgentRunTracer — enabled flag via DI, fail-safe no-op (A + C).

Closes the langfuse_enabled module-global finding: enabled is a constructor
field, exercised here without monkeypatching any module-level state.
"""

import uuid

import langfuse
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    SecurityMessages,
    Verdict,
)
from app.agent.tracing import AgentRunSpan, AgentRunTracer, _NoOpSpan

_IDS = dict(
    content="hi",
    user_id=uuid.uuid4(),
    thread_id=uuid.uuid4(),
    project_id=uuid.uuid4(),
)
_RESULT = GuardResult(
    verdict=Verdict.INJECTION,
    checkpoint=Checkpoint.FINAL_OUTPUT,
    direction=Direction.OUTBOUND,
    detection_layer=DetectionLayer.LLM_CLASSIFIER,
)


def test_disabled_tracer_yields_noop_span() -> None:
    tracer = AgentRunTracer(enabled=False, security_messages=SecurityMessages())
    with tracer.run(**_IDS) as span:
        assert span.trace_id is None
        assert span.callback_handler is None
        # None of these touch Langfuse or raise.
        span.score(Verdict.CLEAN, None)
        span.finalize_blocked(_RESULT)
        span.set_output("done")
        span.record_mid_stream_hit(
            thread_id=_IDS["thread_id"],
            full_response="full",
            tail="tail",
            result=_RESULT,
            chunks_processed=3,
        )


def test_enabled_tracer_degrades_when_client_raises(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("langfuse unavailable")

    monkeypatch.setattr(langfuse, "get_client", _boom)
    tracer = AgentRunTracer(enabled=True, security_messages=SecurityMessages())
    with tracer.run(**_IDS) as span:
        # Setup failed → falls back to no-op span, no exception escapes.
        assert span.trace_id is None
        span.set_output("done")


class _FakeObs:
    def __init__(self) -> None:
        self.update_kwargs: dict | None = None

    def __enter__(self) -> "_FakeObs":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def update(self, **kwargs) -> None:
        self.update_kwargs = kwargs


class _FakeClient:
    def __init__(self, obs: _FakeObs) -> None:
        self._obs = obs

    def start_as_current_observation(self, **kwargs) -> _FakeObs:
        return self._obs


def test_record_mid_stream_hit_builds_observation(monkeypatch) -> None:
    import langfuse as _lf

    obs = _FakeObs()
    monkeypatch.setattr(_lf, "get_client", lambda: _FakeClient(obs))
    span = AgentRunSpan(
        _NoOpSpan(), None, enabled=True, security_messages=SecurityMessages()
    )
    span.record_mid_stream_hit(
        thread_id=_IDS["thread_id"],
        full_response="full response text",
        tail="tail",
        result=_RESULT,
        chunks_processed=3,
    )
    assert obs.update_kwargs is not None
    assert obs.update_kwargs["output"]["verdict"] == "INJECTION"
    meta = obs.update_kwargs["metadata"]
    assert meta["mode"] == "mid_stream"
    assert meta["chunks_processed"] == 3
    assert meta["tail_snapshot"] == "tail"
    assert meta["response_length"] == len("full response text")
