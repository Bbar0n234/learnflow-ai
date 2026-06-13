from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Checkpoint(StrEnum):
    USER_INPUT = "user_input"
    TOOL_RESULT = "tool_result"
    TOOL_CALL_ARG = "tool_call_arg"
    FINAL_OUTPUT = "final_output"
    MCP_METADATA = "mcp_metadata"
    CUSTOM_INSTRUCTIONS_WRITE = "custom_instructions_write"
    KS_WRITE_REST = "ks_write_rest"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


_DIRECTION_MAP: dict[Checkpoint, Direction] = {
    Checkpoint.USER_INPUT: Direction.INBOUND,
    Checkpoint.TOOL_RESULT: Direction.INBOUND,
    Checkpoint.MCP_METADATA: Direction.INBOUND,
    Checkpoint.CUSTOM_INSTRUCTIONS_WRITE: Direction.INBOUND,
    Checkpoint.KS_WRITE_REST: Direction.INBOUND,
    Checkpoint.TOOL_CALL_ARG: Direction.OUTBOUND,
    Checkpoint.FINAL_OUTPUT: Direction.OUTBOUND,
}


def direction_of(checkpoint: Checkpoint) -> Direction:
    return _DIRECTION_MAP[checkpoint]


class DetectionLayer(StrEnum):
    CANARY = "canary"
    UNICODE = "unicode"
    FRAGMENT = "fragment"
    PAIRED = "paired"
    LLM_CLASSIFIER = "llm_classifier"
    GRACEFUL_DEGRADATION = "graceful_degradation"


class Verdict(StrEnum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    INJECTION = "INJECTION"


# Single source of truth for verdict → Langfuse observation level.
VERDICT_TO_LEVEL: dict[Verdict, str] = {
    Verdict.CLEAN: "DEFAULT",
    Verdict.SUSPICIOUS: "WARNING",
    Verdict.INJECTION: "ERROR",
}


class GuardResult(BaseModel):
    verdict: Verdict
    checkpoint: Checkpoint
    direction: Direction
    detection_layer: DetectionLayer | None = None
    details: dict[str, Any] | None = None
    duration_ms: int = 0


class ClassifierResult(BaseModel):
    verdict: Verdict
    reasoning: str | None = None
    retries: int = 0


class PairedDetectorConfig(BaseModel):
    min_compromised_tools: int = 3
    min_params_per_tool: int = 1


class FragmentDetectorConfig(BaseModel):
    window_size: int = 60
    stride: int = 30
    min_unique_matches: int = 2


class DetectorsConfig(BaseModel):
    paired: PairedDetectorConfig = PairedDetectorConfig()
    fragment: FragmentDetectorConfig = FragmentDetectorConfig()


class CheckpointConfig(BaseModel):
    description: str = ""
    classifier_enabled: bool = True
    specifics: str = ""


class ReasoningOptions(BaseModel):
    effort: str | None = None


class LLMExtraBody(BaseModel):
    include_reasoning: bool = False
    reasoning: ReasoningOptions | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.include_reasoning:
            data["include_reasoning"] = True
        if self.reasoning is not None:
            reasoning = self.reasoning.model_dump(exclude_none=True)
            if reasoning:
                data["reasoning"] = reasoning
        return data


class LLMClassifierConfig(BaseModel):
    model: str
    extra_body: LLMExtraBody = LLMExtraBody()
    max_retries: int = 3
    temperature: float = 0.0


class SecurityMessages(BaseModel):
    redacted_user_facing: str = "[Сообщение скрыто в целях безопасности]"
    redacted_tool_result: str = "[Tool result blocked by security policy]"


class SecurityConfig(BaseModel):
    llm_classifier: LLMClassifierConfig
    detectors: DetectorsConfig = DetectorsConfig()
    checkpoints: dict[Checkpoint, CheckpointConfig] = {}
    messages: SecurityMessages = SecurityMessages()
