"""Canary for the shared Redis test fixture (learnflow_testing plugin).

Proves the session-scoped ``redis_container`` / function-scoped ``redis_client``
fixture comes up and that ``TraceStore`` round-trips through it. This is a smoke
canary for the fixture itself — full ``TraceStore`` behaviour coverage (TTL,
feedback delete, batch edges) is Ф5c/S8 work, not here.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import redis.asyncio as aioredis
from app.repositories import TraceStore

pytestmark = pytest.mark.integration


async def test_trace_store_round_trips_through_redis_fixture(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)
    thread_id = uuid4()

    await store.save(thread_id, message_id="m1", trace_id="trace-abc")

    assert await store.get_by_thread(thread_id) == {"m1": "trace-abc"}


async def test_redis_client_fixture_is_isolated_per_test(
    redis_client: aioredis.Redis,
) -> None:
    # A leak from the previous test would surface here as a non-empty db.
    assert await redis_client.dbsize() == 0
