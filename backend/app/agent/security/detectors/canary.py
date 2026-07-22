from __future__ import annotations

from typing import Any

from app.agent.security.detectors.base import Hit
from app.agent.security.types import Checkpoint, DetectionLayer


def check_canary_in_text(text: str, canary_token: str) -> bool:
    if not canary_token:
        return False
    return canary_token in text


class CanaryDetector:
    name = "canary"
    layer = DetectionLayer.CANARY
    applies_to = frozenset(
        {
            Checkpoint.USER_INPUT,
            Checkpoint.TOOL_RESULT,
            Checkpoint.TOOL_CALL_ARG,
            Checkpoint.FINAL_OUTPUT,
            Checkpoint.CUSTOM_INSTRUCTIONS_WRITE,
            Checkpoint.KS_WRITE_REST,
            Checkpoint.SKILL_CONTEXT_WRITE,
        }
    )

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None:
        canary_token = ctx.get("canary_token") or ""
        if not canary_token:
            return None
        if canary_token in buffer:
            return Hit(layer=self.layer, details={"canary_token": canary_token})
        return None
