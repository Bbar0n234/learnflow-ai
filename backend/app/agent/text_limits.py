"""Shared truncation policy for stream payloads and history parts.

One limit, one flag, reused everywhere a tool/args/result/task string reaches
the wire (SSE token/updates/custom channels — T1.3–T1.5 — and the persisted
``tool_call`` typed part — T1.7): design-brief § «Лимиты и параметры» requires
truncation in both the SSE contract and the API, and a single helper keeps the
two from drifting apart.
"""

from __future__ import annotations

from typing import Final

# Business invariant, not environment config (conventions.md § Env vs
# константы): a fixed product decision on how much of a tool call's
# args/result (or the agent's task handed to a subagent) surfaces raw before
# the client has to expand it — not something an operator tunes per
# deployment.
TRUNCATION_LIMIT: Final = 2000


def truncate(text: str, limit: int = TRUNCATION_LIMIT) -> tuple[str, bool]:
    """Truncate ``text`` to ``limit`` characters.

    Returns ``(text, truncated)`` — the (possibly shortened) text and whether
    truncation actually happened, mirroring the ``truncated`` flag carried on
    the wire alongside the truncated field itself.
    """
    if len(text) <= limit:
        return text, False
    return text[:limit], True
