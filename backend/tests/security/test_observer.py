"""GuardObserver / ObservationHandle: fail-safe, no-op without a Langfuse client.

The observer must never crash the guard when Langfuse is disabled or absent —
every handle method swallows errors. With ``enabled=False`` (or no client) the
context yields a usable handle whose methods are inert. We assert that contract,
not Langfuse wire behavior (that needs a live client and is out of unit scope).
"""

from __future__ import annotations

from typing import Any

import pytest
from app.agent.security.observer import GuardObserver, ObservationHandle
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    Verdict,
)


class _SpyObservation:
    """Duck-typed stand-in for a Langfuse observation: records update/score calls.

    We assert the *payload our code builds* (verdict, level, blocked flag) — not
    Langfuse wire behavior — by handing this spy to ``ObservationHandle`` directly
    in place of a real observation.
    """

    def __init__(self) -> None:
        self.update_calls: list[dict[str, Any]] = []
        self.score_calls: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.update_calls.append(kwargs)

    def score_trace(self, **kwargs: Any) -> None:
        self.score_calls.append(kwargs)


class _RaisingObservation:
    """Observation whose every call raises — models a misbehaving Langfuse SDK.

    The fail-safe contract is that the guard never lets an observability error
    bubble into the request. We assert that by handing this to the handle and
    proving the handle methods still return normally — exercising the
    ``contextlib.suppress`` blocks, which a ``None`` observation never enters.
    """

    def update(self, **kwargs: Any) -> None:
        raise RuntimeError("langfuse update exploded")

    def score_trace(self, **kwargs: Any) -> None:
        raise RuntimeError("langfuse score exploded")


@pytest.mark.unit
async def test_observe_disabled_yields_inert_handle() -> None:
    observer = GuardObserver(enabled=False)

    async with observer.observe(
        Checkpoint.USER_INPUT, "content", enabled=False
    ) as handle:
        assert isinstance(handle, ObservationHandle)


@pytest.mark.unit
async def test_observe_without_client_finalize_does_not_raise() -> None:
    observer = GuardObserver(enabled=False)

    result = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=Direction.INBOUND,
    )

    async with observer.observe(Checkpoint.USER_INPUT, "content") as handle:
        # Must not raise even though no Langfuse observation backs the handle.
        handle.finalize(result)


@pytest.mark.unit
@pytest.mark.parametrize(
    "verdict", [Verdict.CLEAN, Verdict.SUSPICIOUS, Verdict.INJECTION]
)
def test_observation_handle_finalize_is_noop_without_observations(
    verdict: Verdict,
) -> None:
    handle = ObservationHandle(None, root_obs=None)
    result = GuardResult(
        verdict=verdict,
        checkpoint=Checkpoint.FINAL_OUTPUT,
        direction=Direction.OUTBOUND,
    )

    # No-op: nothing to assert beyond "does not raise" — fail-safe contract.
    handle.finalize(result)


@pytest.mark.unit
def test_observation_handle_generation_methods_are_fail_safe() -> None:
    handle = ObservationHandle(None)

    # No Langfuse generation started; these must all be inert, not crash.
    handle.update_generation(raw_output="INJECTION", token_usage=None)
    handle._close_generation()


@pytest.mark.unit
def test_finalize_swallows_observation_errors() -> None:
    # Both sinks raise on every call; finalize must absorb the failures so a
    # broken Langfuse SDK cannot crash the guard. A None observation would skip
    # the suppress blocks entirely, so we use a live raising one to reach them.
    handle = ObservationHandle(_RaisingObservation(), root_obs=_RaisingObservation())
    result = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.FINAL_OUTPUT,
        direction=Direction.OUTBOUND,
    )

    # Returns normally despite update()/score_trace() raising underneath.
    handle.finalize(result)


@pytest.mark.unit
def test_generation_methods_swallow_observation_errors() -> None:
    # A started generation whose update/close raise — the suppress blocks in
    # update_generation/_close_generation must absorb it (fail-safe).
    handle = ObservationHandle(None)
    handle._gen_obs = _RaisingObservation()

    handle.update_generation(raw_output="INJECTION", token_usage=None)
    handle._close_generation(error=True)


# --- finalize: the payload our code builds over a verdict ------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verdict", "expected_level"),
    [
        (Verdict.CLEAN, "DEFAULT"),
        (Verdict.SUSPICIOUS, "WARNING"),
        (Verdict.INJECTION, "ERROR"),
    ],
)
def test_finalize_sets_guard_observation_level_per_verdict(
    verdict: Verdict, expected_level: str
) -> None:
    guard_obs = _SpyObservation()
    handle = ObservationHandle(guard_obs, root_obs=None)
    result = GuardResult(
        verdict=verdict,
        checkpoint=Checkpoint.USER_INPUT,
        direction=Direction.INBOUND,
    )

    handle.finalize(result)

    assert len(guard_obs.update_calls) == 1
    call = guard_obs.update_calls[0]
    # Observability level mirrors VERDICT_TO_LEVEL, not the block/redact decision.
    assert call["level"] == expected_level
    assert call["output"]["verdict"] == verdict.value


@pytest.mark.unit
@pytest.mark.parametrize(
    ("verdict", "blocked"),
    [
        (Verdict.CLEAN, False),
        (Verdict.SUSPICIOUS, False),
        (Verdict.INJECTION, True),
    ],
)
def test_finalize_marks_root_trace_blocked_only_on_injection(
    verdict: Verdict, blocked: bool
) -> None:
    root_obs = _SpyObservation()
    handle = ObservationHandle(None, root_obs=root_obs)
    result = GuardResult(
        verdict=verdict,
        checkpoint=Checkpoint.FINAL_OUTPUT,
        direction=Direction.OUTBOUND,
    )

    handle.finalize(result)

    # The root trace is scored and updated; only INJECTION flips blocked=True.
    assert root_obs.score_calls[0]["name"] == "security_verdict"
    assert root_obs.score_calls[0]["value"] == verdict.value
    assert root_obs.update_calls[0]["output"]["blocked"] is blocked
    assert root_obs.update_calls[0]["metadata"]["blocked"] is blocked


@pytest.mark.unit
def test_finalize_propagates_detection_layer_and_details_into_metadata() -> None:
    guard_obs = _SpyObservation()
    handle = ObservationHandle(guard_obs, root_obs=None)
    result = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=Direction.INBOUND,
        detection_layer=DetectionLayer.CANARY,
        details={"reason": "canary-token-leak"},
    )

    handle.finalize(result)

    metadata = guard_obs.update_calls[0]["metadata"]
    assert metadata["detection_layer"] == DetectionLayer.CANARY.value
    assert metadata["details"] == {"reason": "canary-token-leak"}
