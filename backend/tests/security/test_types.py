"""Verdict/Checkpoint type tables — the two layers that must not be conflated.

``VERDICT_TO_LEVEL`` is the Langfuse *observability* level (not block/redact);
``direction_of`` maps a checkpoint to inbound/outbound. Both are single sources
of truth, so a dedicated guard catches silent drift.
"""

from __future__ import annotations

import pytest
from app.agent.security.types import (
    VERDICT_TO_LEVEL,
    Checkpoint,
    Direction,
    LLMExtraBody,
    ReasoningOptions,
    Verdict,
    direction_of,
)


@pytest.mark.unit
def test_verdict_to_level_is_the_observability_mapping() -> None:
    # Observability level, NOT the action layer (which gates on INJECTION only).
    assert VERDICT_TO_LEVEL == {
        Verdict.CLEAN: "DEFAULT",
        Verdict.SUSPICIOUS: "WARNING",
        Verdict.INJECTION: "ERROR",
    }


@pytest.mark.unit
def test_verdict_to_level_covers_every_verdict() -> None:
    assert set(VERDICT_TO_LEVEL) == set(Verdict)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("checkpoint", "expected"),
    [
        (Checkpoint.USER_INPUT, Direction.INBOUND),
        (Checkpoint.TOOL_RESULT, Direction.INBOUND),
        (Checkpoint.MCP_METADATA, Direction.INBOUND),
        (Checkpoint.CUSTOM_INSTRUCTIONS_WRITE, Direction.INBOUND),
        (Checkpoint.KS_WRITE_REST, Direction.INBOUND),
        (Checkpoint.TOOL_CALL_ARG, Direction.OUTBOUND),
        (Checkpoint.FINAL_OUTPUT, Direction.OUTBOUND),
    ],
)
def test_direction_of_maps_each_checkpoint(
    checkpoint: Checkpoint, expected: Direction
) -> None:
    assert direction_of(checkpoint) is expected


@pytest.mark.unit
def test_direction_of_covers_every_checkpoint() -> None:
    # No checkpoint silently missing from the direction map.
    for cp in Checkpoint:
        assert direction_of(cp) in (Direction.INBOUND, Direction.OUTBOUND)


# --- LLMExtraBody.as_dict: only emit set fields ---------------------------


@pytest.mark.unit
def test_extra_body_defaults_to_empty_dict() -> None:
    # Nothing enabled -> no extra body sent to the model.
    assert LLMExtraBody().as_dict() == {}


@pytest.mark.unit
def test_extra_body_emits_include_reasoning_flag() -> None:
    assert LLMExtraBody(include_reasoning=True).as_dict() == {"include_reasoning": True}


@pytest.mark.unit
def test_extra_body_emits_reasoning_options_dropping_none() -> None:
    body = LLMExtraBody(reasoning=ReasoningOptions(effort="high"))

    assert body.as_dict() == {"reasoning": {"effort": "high"}}


@pytest.mark.unit
def test_extra_body_omits_empty_reasoning_options() -> None:
    # effort=None collapses to an empty dict after exclude_none -> field dropped.
    body = LLMExtraBody(reasoning=ReasoningOptions(effort=None))

    assert body.as_dict() == {}
