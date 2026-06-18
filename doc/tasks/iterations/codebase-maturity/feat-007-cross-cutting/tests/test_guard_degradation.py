"""
Point tests: T3.2 / T3.5 / T3.6 / T3.7 / T3.8 / T3.9 — Guard degradation (feat-007, T3)

Tests the observable guard-degradation paths:
  T3.2 — import smoke: AGENT_GUARD_DEGRADED importable, correct value
  T3.5 — Guard road 1 (LLM exception), INBOUND checkpoint → GRACEFUL_DEGRADATION + agent.guard.degraded
  T3.6 — Guard road 1 (LLM exception), OUTBOUND checkpoint → direction=outbound in log metadata
  T3.7 — Guard road 2 (retries exhausted / degraded=True) → GRACEFUL_DEGRADATION + agent.guard.degraded
  T3.8 — ClassifierResult.degraded signal unit tests (degraded=True vs degraded=False)
  T3.9 — Injection path not affected by degraded branching (regression)

Run from backend directory:
  uv run pytest ../doc/tasks/iterations/codebase-maturity/feat-007-cross-cutting/tests/test_guard_degradation.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from structlog.testing import capture_logs

from app.agent.security.classifier import LLMClassifier
from app.agent.security.guard import SecurityGuard
from app.agent.security.observer import GuardObserver
from app.agent.security.types import (
    Checkpoint,
    ClassifierResult,
    DetectionLayer,
    LLMClassifierConfig,
    SecurityConfig,
    Verdict,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_guard(classify_side_effect=None, classify_return_value=None) -> SecurityGuard:
    """Build a SecurityGuard with a mocked classifier."""
    mock_llm = MagicMock()
    mock_provider = MagicMock()
    mock_provider.get_prompt.return_value = "You are a classifier. Respond with CLEAN, SUSPICIOUS, or INJECTION."

    security_config = SecurityConfig(
        llm_classifier=LLMClassifierConfig(model="mock-model", max_retries=2)
    )
    classifier = LLMClassifier(
        llm=mock_llm,
        prompt_provider=mock_provider,
        security_config=security_config,
        checkpoint_configs={},
    )

    if classify_side_effect is not None:
        classifier.classify = AsyncMock(side_effect=classify_side_effect)  # type: ignore[method-assign]
    elif classify_return_value is not None:
        classifier.classify = AsyncMock(return_value=classify_return_value)  # type: ignore[method-assign]

    observer = GuardObserver(enabled=False)

    return SecurityGuard(
        detectors=[],
        classifier=classifier,
        observer=observer,
        config=security_config,
    )


# ---------------------------------------------------------------------------
# T3.2 — import smoke
# ---------------------------------------------------------------------------


def test_t32_import_smoke() -> None:
    """T3.2: AGENT_GUARD_DEGRADED is importable and has the expected value."""
    from siem_contracts import AGENT_GUARD_DEGRADED  # noqa: PLC0415

    assert AGENT_GUARD_DEGRADED == "agent.guard.degraded"

    # Must be present in EventType Literal (verified via vocabulary module)
    from siem_contracts.vocabulary import EventType  # noqa: PLC0415

    # EventType is a Literal type — check that the string is in its args
    import typing  # noqa: PLC0415

    literal_values = typing.get_args(EventType)
    assert AGENT_GUARD_DEGRADED in literal_values, (
        f"'agent.guard.degraded' not found in EventType Literal args: {literal_values}"
    )


# ---------------------------------------------------------------------------
# T3.5 — Guard road 1: LLM exception, INBOUND checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t35_guard_road1_inbound_llm_exception() -> None:
    """T3.5: LLM raises exception (road 1) → GRACEFUL_DEGRADATION, event_type=agent.guard.degraded, direction=inbound."""
    guard = _make_guard(classify_side_effect=RuntimeError("LLM unavailable"))

    with capture_logs() as cap:
        result = await guard.check(
            "Hello",
            Checkpoint.USER_INPUT,
            observe=False,
        )

    # --- GuardResult assertions ---
    assert result.verdict == Verdict.CLEAN, f"Expected CLEAN, got {result.verdict}"
    assert result.detection_layer == DetectionLayer.GRACEFUL_DEGRADATION, (
        f"Expected GRACEFUL_DEGRADATION, got {result.detection_layer}"
    )
    assert result.details == {"reason": "llm_failure"}, (
        f"Expected reason=llm_failure, got {result.details}"
    )
    assert result.direction.value == "inbound", f"Expected direction=inbound, got {result.direction}"

    # --- Log assertions ---
    degradation_logs = [
        e for e in cap
        if e.get("event_type") == "agent.guard.degraded"
    ]
    assert degradation_logs, (
        f"Expected a log entry with event_type='agent.guard.degraded'. Captured: {cap}"
    )
    log_entry = degradation_logs[0]
    assert log_entry.get("security_event") is True
    assert log_entry.get("severity") == "critical"
    assert log_entry.get("exc_info"), "Expected exc_info to be set for road 1 (LLM exception)"

    metadata = log_entry.get("metadata", {})
    assert metadata.get("checkpoint") == "user_input", f"metadata.checkpoint mismatch: {metadata}"
    assert metadata.get("direction") == "inbound", f"metadata.direction mismatch: {metadata}"
    assert metadata.get("detection_layer") == "graceful_degradation"
    assert metadata.get("verdict") == "clean"

    # Must NOT emit injection event
    injection_logs = [
        e for e in cap
        if "classifier_injection" in str(e.get("event_type", ""))
    ]
    assert not injection_logs, (
        f"Injection event_type must not be emitted on degradation (road 1). Got: {injection_logs}"
    )


# ---------------------------------------------------------------------------
# T3.6 — Guard road 1: LLM exception, OUTBOUND checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t36_guard_road1_outbound_llm_exception() -> None:
    """T3.6: road 1 on OUTBOUND checkpoint → direction=outbound in log (flaw F-AGT-03 fixed)."""
    guard = _make_guard(classify_side_effect=RuntimeError("LLM unavailable"))

    with capture_logs() as cap:
        result = await guard.check(
            "Output text",
            Checkpoint.FINAL_OUTPUT,
            observe=False,
        )

    assert result.verdict == Verdict.CLEAN
    assert result.detection_layer == DetectionLayer.GRACEFUL_DEGRADATION
    assert result.direction.value == "outbound", f"Expected direction=outbound, got {result.direction}"

    degradation_logs = [
        e for e in cap
        if e.get("event_type") == "agent.guard.degraded"
    ]
    assert degradation_logs, f"Expected agent.guard.degraded log. Captured: {cap}"

    metadata = degradation_logs[0].get("metadata", {})
    assert metadata.get("direction") == "outbound", (
        f"Expected direction=outbound in metadata (F-AGT-03 fix). Got: {metadata}"
    )
    assert metadata.get("checkpoint") == "final_output"

    # Confirm no INPUT injection event (the old defect was emitting INPUT event on OUTPUT checkpoint)
    injection_logs = [
        e for e in cap
        if "input" in str(e.get("event_type", "")) and "injection" in str(e.get("event_type", ""))
    ]
    assert not injection_logs, (
        f"Old defect: INPUT injection event on OUTPUT checkpoint. Got: {injection_logs}"
    )


# ---------------------------------------------------------------------------
# T3.7 — Guard road 2: retries exhausted (degraded=True from classifier)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t37_guard_road2_retries_exhausted() -> None:
    """T3.7: classifier returns degraded=True → GRACEFUL_DEGRADATION, agent.guard.degraded observed."""
    # Simulate: classifier exhausted retries and returned ClassifierResult(degraded=True)
    guard = _make_guard(
        classify_return_value=ClassifierResult(
            verdict=Verdict.CLEAN,
            reasoning=None,
            retries=2,
            degraded=True,
        )
    )

    with capture_logs() as cap:
        result = await guard.check(
            "Hello",
            Checkpoint.USER_INPUT,
            observe=False,
        )

    # --- GuardResult assertions ---
    assert result.verdict == Verdict.CLEAN
    assert result.detection_layer == DetectionLayer.GRACEFUL_DEGRADATION, (
        f"Expected GRACEFUL_DEGRADATION, got {result.detection_layer}"
    )
    assert result.details == {"reason": "retries_exhausted"}, (
        f"Expected reason=retries_exhausted, got {result.details}"
    )

    # --- Log assertions: road 2 is now observable (was silent before T3) ---
    degradation_logs = [
        e for e in cap
        if e.get("event_type") == "agent.guard.degraded"
    ]
    assert degradation_logs, (
        "Road 2 (retries exhausted) was silent before T3; now it must emit "
        f"agent.guard.degraded. Captured: {cap}"
    )
    log_entry = degradation_logs[0]
    assert log_entry.get("security_event") is True
    assert log_entry.get("severity") == "critical"
    # Road 2 does not have exc_info (no exception; retries exhausted)
    assert not log_entry.get("exc_info"), (
        "Road 2 should NOT have exc_info (no exception raised); retries_exhausted path."
    )

    metadata = log_entry.get("metadata", {})
    assert metadata.get("detection_layer") == "graceful_degradation"
    assert metadata.get("verdict") == "clean"
    assert metadata.get("direction") in ("inbound", "outbound")

    # Injection event must NOT be emitted (verdict=CLEAN)
    injection_logs = [
        e for e in cap
        if "injection" in str(e.get("event_type", ""))
    ]
    assert not injection_logs, (
        f"Injection event must not fire when verdict=CLEAN (road 2). Got: {injection_logs}"
    )


# ---------------------------------------------------------------------------
# T3.8 — ClassifierResult.degraded signal unit tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t38_classifier_result_degraded_on_retries_exhausted() -> None:
    """T3.8a: LLM always returns invalid verdict → classify() returns ClassifierResult(degraded=True)."""
    mock_llm = MagicMock()
    # Always returns "MAYBE" — not in {"CLEAN", "SUSPICIOUS", "INJECTION"}
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="MAYBE"))

    mock_provider = MagicMock()
    mock_provider.get_prompt.return_value = "classifier prompt"

    security_config = SecurityConfig(
        llm_classifier=LLMClassifierConfig(model="mock-model", max_retries=2)
    )
    classifier = LLMClassifier(
        llm=mock_llm,
        prompt_provider=mock_provider,
        security_config=security_config,
        checkpoint_configs={},
    )

    result = await classifier.classify("test content", Checkpoint.USER_INPUT)

    assert result.degraded is True, f"Expected degraded=True, got {result.degraded}"
    assert result.retries == 2, f"Expected retries=2 (max_retries), got {result.retries}"
    assert result.verdict == Verdict.CLEAN


@pytest.mark.anyio
async def test_t38_classifier_result_not_degraded_on_valid_verdict() -> None:
    """T3.8b: LLM returns 'CLEAN' → ClassifierResult(degraded=False)."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="CLEAN"))

    mock_provider = MagicMock()
    mock_provider.get_prompt.return_value = "classifier prompt"

    security_config = SecurityConfig(
        llm_classifier=LLMClassifierConfig(model="mock-model", max_retries=2)
    )
    classifier = LLMClassifier(
        llm=mock_llm,
        prompt_provider=mock_provider,
        security_config=security_config,
        checkpoint_configs={},
    )

    result = await classifier.classify("safe content", Checkpoint.USER_INPUT)

    assert result.degraded is False, f"Expected degraded=False, got {result.degraded}"
    assert result.verdict == Verdict.CLEAN
    assert result.retries == 0


# ---------------------------------------------------------------------------
# T3.9 — Injection path not affected by degraded branching (regression)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t39_injection_path_not_affected_by_degraded_branching() -> None:
    """T3.9: Normal injection verdict is not intercepted by the degraded branch."""
    # classifier returns INJECTION (non-degraded)
    guard = _make_guard(
        classify_return_value=ClassifierResult(
            verdict=Verdict.INJECTION,
            reasoning="Prompt injection detected",
            retries=0,
            degraded=False,
        )
    )

    # Test INBOUND injection
    with capture_logs() as cap_inbound:
        result_inbound = await guard.check(
            "Malicious input",
            Checkpoint.USER_INPUT,
            observe=False,
        )

    assert result_inbound.verdict == Verdict.INJECTION, (
        f"Expected INJECTION verdict, got {result_inbound.verdict}"
    )
    assert result_inbound.detection_layer == DetectionLayer.LLM_CLASSIFIER, (
        f"Expected LLM_CLASSIFIER detection_layer, got {result_inbound.detection_layer}"
    )

    injection_logs_inbound = [
        e for e in cap_inbound
        if "injection" in str(e.get("event_type", ""))
    ]
    assert injection_logs_inbound, (
        f"Expected injection log for INBOUND. Captured: {cap_inbound}"
    )
    assert (
        injection_logs_inbound[0].get("event_type")
        == "agent.guard.input.classifier_injection"
    ), f"Wrong event_type for INBOUND injection: {injection_logs_inbound[0].get('event_type')}"

    # No degradation event
    degradation_logs_inbound = [
        e for e in cap_inbound if e.get("event_type") == "agent.guard.degraded"
    ]
    assert not degradation_logs_inbound, (
        "Degradation event must not fire for a real injection verdict."
    )

    # Test OUTBOUND injection
    with capture_logs() as cap_outbound:
        result_outbound = await guard.check(
            "Malicious output",
            Checkpoint.FINAL_OUTPUT,
            observe=False,
        )

    assert result_outbound.verdict == Verdict.INJECTION
    injection_logs_outbound = [
        e for e in cap_outbound
        if "injection" in str(e.get("event_type", ""))
    ]
    assert injection_logs_outbound
    assert (
        injection_logs_outbound[0].get("event_type")
        == "agent.guard.output.classifier_injection"
    ), f"Wrong event_type for OUTBOUND injection: {injection_logs_outbound[0].get('event_type')}"
