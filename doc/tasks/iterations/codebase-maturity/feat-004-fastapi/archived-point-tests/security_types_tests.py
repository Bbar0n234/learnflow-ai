"""Регрессия StrEnum-миграции: значения и сериализация security-энумов.

Контракт: `.value` каждого члена идентичен до-миграционному `(str, Enum)`;
Pydantic сериализует по value. Эти значения уходят в SIEM event pipeline
и Langfuse — менять их нельзя.
"""

from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    Verdict,
)


def test_checkpoint_values_unchanged() -> None:
    assert Checkpoint.USER_INPUT.value == "user_input"
    assert Checkpoint.TOOL_RESULT.value == "tool_result"
    assert Checkpoint.TOOL_CALL_ARG.value == "tool_call_arg"
    assert Checkpoint.FINAL_OUTPUT.value == "final_output"
    assert Checkpoint.MCP_METADATA.value == "mcp_metadata"
    assert Checkpoint.CUSTOM_INSTRUCTIONS_WRITE.value == "custom_instructions_write"
    assert Checkpoint.KS_WRITE_REST.value == "ks_write_rest"


def test_verdict_and_layer_values_unchanged() -> None:
    assert Verdict.CLEAN.value == "CLEAN"
    assert Verdict.SUSPICIOUS.value == "SUSPICIOUS"
    assert Verdict.INJECTION.value == "INJECTION"
    assert Direction.INBOUND.value == "inbound"
    assert Direction.OUTBOUND.value == "outbound"
    assert DetectionLayer.LLM_CLASSIFIER.value == "llm_classifier"


def test_strenum_str_equals_value() -> None:
    # StrEnum: str(member) == value — на это полагается сериализация в логи/события
    assert str(Checkpoint.USER_INPUT) == "user_input"
    assert f"{Verdict.INJECTION}" == "INJECTION"


def test_guard_result_serializes_by_value() -> None:
    result = GuardResult(
        verdict=Verdict.INJECTION,
        checkpoint=Checkpoint.USER_INPUT,
        direction=Direction.INBOUND,
        detection_layer=DetectionLayer.CANARY,
    )
    dumped = result.model_dump(mode="json")
    assert dumped["verdict"] == "INJECTION"
    assert dumped["checkpoint"] == "user_input"
    assert dumped["direction"] == "inbound"
    assert dumped["detection_layer"] == "canary"
