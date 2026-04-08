import unicodedata

# Unicode General Categories used in prompt injection attacks:
#   Cf (Format)     — zero-width space, soft hyphen, RTL/LTR override, BOM
#   Co (Private Use) — PUA characters (U+E000–U+F8FF)
#   Cn (Unassigned)  — unused codepoints, no legitimate text use
_SUSPICIOUS_CATEGORIES = frozenset(("Cf", "Co", "Cn"))


def detect_invisible_chars(text: str) -> bool:
    """Detect invisible Unicode characters used in prompt injection.

    Returns True if any suspicious invisible characters are found.
    ASCII characters and normal visible Unicode (Cyrillic, CJK, emoji) pass through.
    """
    for char in text:
        if ord(char) <= 127:
            continue
        if unicodedata.category(char) in _SUSPICIOUS_CATEGORIES:
            return True
    return False


def check_canary_in_text(text: str, canary_token: str) -> bool:
    """Check if canary token appears in text (substring match)."""
    if not canary_token:
        return False
    return canary_token in text
