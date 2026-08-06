"""Canary token generation — deterministic HMAC over (thread_id, secret)."""

from __future__ import annotations

import pytest
from app.agent.security.canary import generate_canary_token


@pytest.mark.unit
def test_generate_canary_token_is_deterministic_for_same_inputs() -> None:
    a = generate_canary_token("thread-123", "secret")
    b = generate_canary_token("thread-123", "secret")

    assert a == b


@pytest.mark.unit
def test_generate_canary_token_is_16_char_hex() -> None:
    token = generate_canary_token("thread-123", "secret")

    assert len(token) == 16
    # All chars are lowercase hex digits.
    assert all(c in "0123456789abcdef" for c in token)


@pytest.mark.unit
def test_generate_canary_token_differs_by_thread() -> None:
    a = generate_canary_token("thread-aaa", "secret")
    b = generate_canary_token("thread-bbb", "secret")

    assert a != b


@pytest.mark.unit
def test_generate_canary_token_differs_by_secret() -> None:
    a = generate_canary_token("thread-123", "secret-one")
    b = generate_canary_token("thread-123", "secret-two")

    assert a != b
