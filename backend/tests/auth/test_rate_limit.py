"""Rate limiter: solitary-unit on the sliding window + HTTP wiring checks.

The window (infra/rate_limit.py) reads ``time.monotonic()`` directly, so the
clock is the only collaborator worth faking — injected via monkeypatch to make
window expiry deterministic without sleeping.

The integration cases prove each route is wired to a *distinct* limiter key:
login keys on ``name:ip``, register and refresh on ``ip`` alone, with their own
budgets — a regression that swapped or merged the keys would surface here.
"""

from __future__ import annotations

import pytest
from app.infra.rate_limit import RateLimiter
from httpx import AsyncClient

from tests.auth._helpers import login, register


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
    allowed, retry_after = limiter.is_allowed("k", 3, 60)

    assert verdicts == [True, True, True]
    assert allowed is False  # fourth call over the budget
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
    assert response.json()["detail"] == "Слишком много запросов, попробуйте позже"
    assert "retry-after" in {k.lower() for k in response.headers}


@pytest.mark.integration
async def test_register_over_limit_returns_429_with_retry_after(
    auth_client: AsyncClient,
) -> None:
    # Register allows 3 attempts per window keyed on IP alone (no username), so
    # distinct usernames from the same client share one budget; the 4th is 429.
    statuses = []
    for i in range(4):
        response = await register(auth_client, name=f"newcomer-{i}")
        statuses.append(response.status_code)

    assert statuses[:3] == [200, 200, 200]
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте позже"
    assert "retry-after" in {k.lower() for k in response.headers}


@pytest.mark.integration
async def test_refresh_over_limit_returns_429_with_retry_after(
    auth_client: AsyncClient,
) -> None:
    # Refresh allows 10 attempts per window keyed on IP alone; the rate gate
    # runs before the cookie check, so cookieless 401s still burn the budget.
    auth_client.cookies.clear()
    statuses = []
    for _ in range(11):
        response = await auth_client.post("/api/auth/refresh")
        statuses.append(response.status_code)

    assert statuses[:10] == [401] * 10
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте позже"
    assert "retry-after" in {k.lower() for k in response.headers}
