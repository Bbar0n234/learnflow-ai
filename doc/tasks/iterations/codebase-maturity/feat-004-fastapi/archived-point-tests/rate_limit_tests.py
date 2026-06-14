"""Автотесты RateLimiter (критичный путь auth, теперь в app.state)."""

from app.infra.rate_limit import RateLimiter


def test_allows_under_limit() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        allowed, retry_after = limiter.is_allowed("k", 5, 60)
        assert allowed
        assert retry_after is None


def test_blocks_over_limit_with_retry_after() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.is_allowed("k", 5, 60)
    allowed, retry_after = limiter.is_allowed("k", 5, 60)
    assert not allowed
    assert retry_after is not None and retry_after >= 1


def test_keys_are_independent() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.is_allowed("k1", 5, 60)
    allowed, _ = limiter.is_allowed("k2", 5, 60)
    assert allowed


def test_instances_are_isolated() -> None:
    # Состояние больше не module-level: два экземпляра не делят buckets
    a, b = RateLimiter(), RateLimiter()
    for _ in range(5):
        a.is_allowed("k", 5, 60)
    allowed, _ = b.is_allowed("k", 5, 60)
    assert allowed
