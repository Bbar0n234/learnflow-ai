from __future__ import annotations

import re

_WS = re.compile(r"\s+")
# Two adjacent alnum tokens separated by a single space → merged with `_`.
# Run iteratively: overlapping matches like "save user memory" need two passes.
_WORD_GAP = re.compile(r"([A-Za-z0-9])\s+(?=[A-Za-z0-9])")


def normalize(text: str) -> str:
    """Lowercase + collapse ``-``/``_``/inner whitespace into ``_``.

    Shared helper for fragment + paired detectors so the corpus and runtime
    buffers match on the same canonical form. Whitespace *inside* a tool
    name (``save user memory``) is collapsed to ``_`` so the paired detector
    matches the canonical registry form (``save_user_memory``).
    """
    lowered = text.lower()
    lowered = lowered.replace("-", "_")
    lowered = _WS.sub(" ", lowered).strip()
    # Replace single space between alnum characters with `_`, preserving
    # punctuation-separated tokens untouched.
    prev = None
    while prev != lowered:
        prev = lowered
        lowered = _WORD_GAP.sub(r"\1_", lowered)
    return lowered
