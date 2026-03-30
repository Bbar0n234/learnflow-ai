from __future__ import annotations

from uuid import UUID

import redis.asyncio as aioredis


class TraceStore:
    """Redis-backed mapping: (thread_id, message_id) -> trace_id.

    Uses Redis HASHes keyed by `trace:{thread_id}`.
    Each hash field is a message_id, value is a trace_id.
    TTL is refreshed on every write.
    """

    TTL = 30 * 24 * 3600  # 30 days

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis

    async def save(self, thread_id: UUID, message_id: str, trace_id: str) -> None:
        key = f"trace:{thread_id}"
        await self._redis.hset(key, message_id, trace_id)  # type: ignore[misc]
        await self._redis.expire(key, self.TTL)

    async def get_by_thread(self, thread_id: UUID) -> dict[str, str]:
        key = f"trace:{thread_id}"
        raw: dict[bytes, bytes] = await self._redis.hgetall(key)  # type: ignore[misc]
        return {k.decode(): v.decode() for k, v in raw.items()}

    # --- Feedback score persistence ---

    async def save_feedback(self, trace_id: str, score: bool | None) -> None:
        key = f"feedback:{trace_id}"
        if score is None:
            await self._redis.delete(key)
        else:
            await self._redis.set(key, "1" if score else "0", ex=self.TTL)

    async def get_feedback_batch(self, trace_ids: list[str]) -> dict[str, bool]:
        if not trace_ids:
            return {}
        keys = [f"feedback:{tid}" for tid in trace_ids]
        values: list[bytes | None] = await self._redis.mget(keys)
        result: dict[str, bool] = {}
        for tid, val in zip(trace_ids, values, strict=True):
            if val is not None:
                result[tid] = val == b"1"
        return result
