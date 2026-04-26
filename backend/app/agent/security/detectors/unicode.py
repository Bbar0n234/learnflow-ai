from __future__ import annotations

import unicodedata
from typing import Any

from app.agent.security.detectors.base import Hit
from app.agent.security.detectors.canary import check_canary_in_text
from app.agent.security.types import Checkpoint, DetectionLayer

# Unicode General Categories used in prompt injection attacks:
#   Cf (Format)      — zero-width space, soft hyphen, RTL/LTR override, BOM
#   Co (Private Use) — PUA characters (U+E000–U+F8FF)
#   Cn (Unassigned)  — unused codepoints, no legitimate text use
_SUSPICIOUS_CATEGORIES = frozenset(("Cf", "Co", "Cn"))


def detect_invisible_chars(text: str) -> bool:
    for char in text:
        if ord(char) <= 127:
            continue
        if unicodedata.category(char) in _SUSPICIOUS_CATEGORIES:
            return True
    return False


__all__ = ["UnicodeDetector", "check_canary_in_text", "detect_invisible_chars"]


class UnicodeDetector:
    name = "unicode"
    layer = DetectionLayer.UNICODE
    applies_to = frozenset(
        {
            Checkpoint.USER_INPUT,
            Checkpoint.TOOL_RESULT,
            Checkpoint.MCP_METADATA,
            Checkpoint.CUSTOM_INSTRUCTIONS_WRITE,
            Checkpoint.KS_WRITE_REST,
        }
    )

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None:
        if detect_invisible_chars(buffer):
            return Hit(layer=self.layer, details={})
        return None
