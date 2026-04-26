"""Map internal exceptions to user-safe SSE ``error`` detail strings.

Keeps technical details (paths, tool names, stack traces, internal
identifiers) out of the channel that bypasses the security classifier.
Texts are sourced from ``configs/error_messages.yaml`` so they can be
edited without a code change.
"""

from __future__ import annotations

import asyncio

from app.agent.config import ErrorMessagesConfig


def normalize_error_message(exc: BaseException, messages: ErrorMessagesConfig) -> str:
    """Return a sanitized, user-facing message for a raised exception."""
    if isinstance(exc, asyncio.CancelledError):
        return messages.cancelled
    if isinstance(exc, asyncio.TimeoutError):
        return messages.timeout

    name = type(exc).__name__.lower()
    if "timeout" in name:
        return messages.timeout
    if "auth" in name or "permission" in name or "forbidden" in name:
        return messages.auth
    if "connection" in name or "network" in name or "upstream" in name:
        return messages.upstream
    return messages.generic
