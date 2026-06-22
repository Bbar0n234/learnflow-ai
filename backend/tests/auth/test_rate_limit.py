"""Rate limiter: solitary-unit on the sliding window + one HTTP wiring check.

The window (infra/rate_limit.py) reads ``time.monotonic()`` directly, so the
clock is the only collaborator worth faking — injected via monkeypatch to make
window expiry deterministic without sleeping.
"""

from __future__ import annotations

import pytest
from app.infra.rate_limit import RateLimiter
from httpx import AsyncClient

from tests.auth._helpers import login


class FakeClock:
    """Monotonic clock stand-in with explicit advancement."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake = FakeClock()
    # Patch the name as the module under test reads it (``time.monotonic`` inside
    # app.infra.rate_limit); monkeypatch restores it after the test.
    monkeypatch.setattr("app.infra.rate_limit.time.monotonic", fake)
    return fake


@pytest.mark.unit
def test_allows_up_to_limit_then_blocks(clock: FakeClock) -> None:
    limiter = RateLimiter()

    verdicts = [limiter.is_allowed("k", max_requests=3, window_seconds=60)[0]]
    verdicts.append(limiter.is_allowed("k", 3, 60)[0])
    verdicts.append(limiter.is_allowed("k", 3, 60)[0])
    blocked, retry_after = limiter.is_allowed("k", 3, 60)

    assert verdicts == [True, True, True]
    assert blocked is False
    assert retry_after is not None and retry_after > 0


@pytest.mark.unit
def test_window_expiry_resets_budget(clock: FakeClock) -> None:
    limiter = RateLimiter()
    for _ in range(3):
        limiter.is_allowed("k", 3, 60)
    assert limiter.is_allowed("k", 3, 60)[0] is False

    clock.advance(61)  # whole window elapsed

    assert limiter.is_allowed("k", 3, 60)[0] is True


@pytest.mark.unit
def test_distinct_keys_have_independent_budgets(clock: FakeClock) -> None:
    limiter = RateLimiter()
    for _ in range(3):
        limiter.is_allowed("a", 3, 60)

    assert limiter.is_allowed("a", 3, 60)[0] is False
    assert limiter.is_allowed("b", 3, 60)[0] is True


@pytest.mark.unit
def test_retry_after_counts_down_to_oldest_timestamp(clock: FakeClock) -> None:
    limiter = RateLimiter()
    for _ in range(3):  # oldest stamped at t=1000
        limiter.is_allowed("k", 3, 60)

    clock.advance(10)  # now t=1010, window 60
    blocked, retry_after = limiter.is_allowed("k", 3, 60)

    assert blocked is False
    # int(oldest + window - now) + 1 == int(1000 + 60 - 1010) + 1
    assert retry_after == 51


@pytest.mark.integration
async def test_login_over_limit_returns_429_with_retry_after(
    auth_client: AsyncClient,
) -> None:
    # Login allows 5 attempts per window per (name, ip); the rate check runs
    # before credential verification, so failed attempts still count.
    statuses = []
    for _ in range(6):
        response = await login(auth_client, name="flooder")
        statuses.append(response.status_code)

    assert statuses[:5] == [401, 401, 401, 401, 401]
    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests"
    assert "retry-after" in {k.lower() for k in response.headers}
