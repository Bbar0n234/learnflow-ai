"""Unit: ``truncate`` — the single truncation policy of the whole contract.

One helper decides how much of a tool's arguments, a tool's result or a
subagent's task reaches the client, on the wire and in the API history alike
(streaming.md § «Лимиты»). Its whole observable behaviour is the boundary: what
counts as "fits" and when the accompanying ``truncated`` flag flips — a
one-character error there either flags untouched payloads or, worse, silently
drops the last character of a payload that was reported as complete.
"""

from __future__ import annotations

import pytest
from app.agent.text_limits import TRUNCATION_LIMIT, truncate

pytestmark = pytest.mark.unit


def test_the_limit_is_the_documented_business_invariant() -> None:
    # 2 000 characters is a product decision fixed in the contract, not an
    # operational knob (design-brief § «Лимиты и параметры»).
    assert TRUNCATION_LIMIT == 2000


@pytest.mark.parametrize(
    ("length", "expected_truncated"),
    [
        (0, False),
        (TRUNCATION_LIMIT - 1, False),
        (TRUNCATION_LIMIT, False),
        (TRUNCATION_LIMIT + 1, True),
        (TRUNCATION_LIMIT * 3, True),
    ],
)
def test_the_flag_flips_exactly_past_the_limit(
    length: int, expected_truncated: bool
) -> None:
    text = "x" * length

    result, truncated = truncate(text)

    assert truncated is expected_truncated
    assert len(result) == min(length, TRUNCATION_LIMIT)


def test_text_at_the_limit_is_returned_untouched() -> None:
    text = "y" * TRUNCATION_LIMIT

    assert truncate(text) == (text, False)


def test_truncation_keeps_the_beginning_of_the_text() -> None:
    # The client shows a preview and offers to expand; the preview has to be
    # the opening of the payload, not an arbitrary window of it.
    text = "head" + "z" * TRUNCATION_LIMIT

    result, truncated = truncate(text)

    assert truncated is True
    assert result.startswith("head")
    assert result == text[:TRUNCATION_LIMIT]


def test_a_caller_may_narrow_the_limit() -> None:
    assert truncate("abcdef", 3) == ("abc", True)
    assert truncate("abc", 3) == ("abc", False)
