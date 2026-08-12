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

# How many distinct codepoints a hit reports. The list travels into a SIEM
# event's metadata, and what identifies a hit is *which* codepoints appeared,
# not how many different ones a large buffer managed to accumulate — a
# pathological input must not turn one event into a megabyte of metadata.
_MAX_REPORTED_CODEPOINTS = 20


def _is_invisible(char: str) -> bool:
    if ord(char) <= 127:
        return False
    return unicodedata.category(char) in _SUSPICIOUS_CATEGORIES


def detect_invisible_chars(text: str) -> bool:
    return any(_is_invisible(char) for char in text)


def invisible_codepoints(text: str) -> list[str]:
    """Distinct suspicious codepoints as ``U+XXXX``, in order of first appearance.

    Distinct, not one entry per occurrence: a soft hyphen repeated four
    hundred times across an extracted PDF page is one fact about the buffer,
    reported once.
    """
    found: dict[str, None] = {}
    for char in text:
        if _is_invisible(char):
            found.setdefault(f"U+{ord(char):04X}", None)
    return list(found)


def sanitize_invisible_chars(text: str) -> str:
    """Drop every suspicious codepoint from ``text``.

    Removal, not replacement: the characters carry no visible glyph, so
    deleting them leaves the text a human (and the model) reads exactly as
    before, minus the channel an invisible instruction would travel through.
    Callers decide *when* this is the right answer instead of a redaction —
    see ``app.agent.tool_guards`` § invisible-char sanitizing.
    """
    if not detect_invisible_chars(text):
        return text
    return "".join(char for char in text if not _is_invisible(char))


__all__ = [
    "UnicodeDetector",
    "check_canary_in_text",
    "detect_invisible_chars",
    "invisible_codepoints",
    "sanitize_invisible_chars",
]


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
            Checkpoint.SKILL_CONTEXT_WRITE,
        }
    )

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None:
        """Report which codepoints fired, not just that something did.

        ``details`` reaches the SIEM event verbatim (``guard.py`` spreads it
        into ``metadata``), and an operator triaging a hit needs the codepoint
        to tell a BOM in extracted text apart from an RTL override placed by
        hand. Filled for every checkpoint the detector applies to, not only
        the ones with a sanitizing policy downstream.
        """
        codepoints = invisible_codepoints(buffer)
        if not codepoints:
            return None
        return Hit(
            layer=self.layer,
            details={
                "codepoints": codepoints[:_MAX_REPORTED_CODEPOINTS],
                "distinct_codepoints": len(codepoints),
            },
        )
