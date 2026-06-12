from __future__ import annotations

import time


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int | None]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - window_seconds

        timestamps = self._buckets.get(key, [])
        # Lazy cleanup: remove expired entries
        timestamps = [t for t in timestamps if t > cutoff]
        self._buckets[key] = timestamps

        if len(timestamps) >= max_requests:
            oldest = timestamps[0]
            retry_after = int(oldest + window_seconds - now) + 1
            return False, retry_after

        timestamps.append(now)
        return True, None
