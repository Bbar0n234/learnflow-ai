"""Unit: ``normalize_error_message`` — exception → user-safe SSE detail string.

Pure function over an exception type; no collaborators, solitary-unit. The map
must never leak internal technicals (paths, tool names) — verified by asserting
the output is exactly one of the curated config messages.
"""

from __future__ import annotations

import asyncio

import pytest
from app.agent.config import ErrorMessagesConfig
from app.agent.error_mapper import normalize_error_message


class _AuthError(Exception):
    pass


class _PermissionDeniedError(Exception):
    pass


class _ConnectionResetError(Exception):
    pass


class _UpstreamUnavailableError(Exception):
    pass


class _RequestTimeoutError(Exception):
    pass


@pytest.fixture
def messages() -> ErrorMessagesConfig:
    return ErrorMessagesConfig()


@pytest.mark.unit
def test_normalize_cancelled_error_returns_cancelled_message(
    messages: ErrorMessagesConfig,
) -> None:
    assert normalize_error_message(asyncio.CancelledError(), messages) == (
        messages.cancelled
    )


@pytest.mark.unit
def test_normalize_asyncio_timeout_returns_timeout_message(
    messages: ErrorMessagesConfig,
) -> None:
    assert normalize_error_message(TimeoutError(), messages) == messages.timeout


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "expected_attr"),
    [
        (_RequestTimeoutError("boom"), "timeout"),
        (_AuthError("token"), "auth"),
        (_PermissionDeniedError("nope"), "auth"),
        (_ConnectionResetError("reset"), "upstream"),
        (_UpstreamUnavailableError("down"), "upstream"),
        (ValueError("anything else"), "generic"),
        (RuntimeError("/secret/path leaked here"), "generic"),
    ],
)
def test_normalize_classifies_by_exception_name(
    exc: Exception, expected_attr: str, messages: ErrorMessagesConfig
) -> None:
    assert normalize_error_message(exc, messages) == getattr(messages, expected_attr)


@pytest.mark.unit
def test_normalize_generic_does_not_leak_exception_text(
    messages: ErrorMessagesConfig,
) -> None:
    detail = normalize_error_message(RuntimeError("/var/secrets/api_key.pem"), messages)

    assert "/var/secrets" not in detail
    assert detail == messages.generic
