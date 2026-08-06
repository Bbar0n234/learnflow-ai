"""``TraceStore`` behaviour against a real Redis (shared ``redis_client`` fixture).

``TraceStore`` is a thin Redis mapping, but the parts worth covering are the ones
a fake ``Redis`` could not prove: that HASH writes refresh the 30-day TTL, that a
``None`` feedback score *deletes* the key (rather than storing a falsy marker),
and that the batch read tolerates missing keys. We drive the real client so the
HSET/EXPIRE/SET/DEL/MGET semantics are the ones under test, not a stub's
re-implementation of them.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import redis.asyncio as aioredis
from app.storage import TraceStore

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


async def test_get_by_thread_returns_empty_for_unknown_thread(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)

    assert await store.get_by_thread(uuid4()) == {}


async def test_save_accumulates_multiple_messages_under_one_thread(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)
    thread_id = uuid4()

    await store.save(thread_id, message_id="m1", trace_id="t1")
    await store.save(thread_id, message_id="m2", trace_id="t2")
    await store.save(thread_id, message_id="m1", trace_id="t1-updated")  # overwrite

    assert await store.get_by_thread(thread_id) == {"m1": "t1-updated", "m2": "t2"}


async def test_save_sets_and_refreshes_thread_ttl(
    redis_client: aioredis.Redis,
) -> None:
    # The mapping must not live forever: every save (re)arms the 30-day TTL on the
    # thread hash. A fake Redis would not enforce that the EXPIRE actually applied.
    store = TraceStore(redis_client)
    thread_id = uuid4()
    key = f"trace:{thread_id}"

    await store.save(thread_id, message_id="m1", trace_id="t1")
    first_ttl = await redis_client.ttl(key)

    assert 0 < first_ttl <= TraceStore.TTL

    # Manually shorten the TTL, then a second save must push it back up to the full
    # window — proving save refreshes (not merely sets-once) the expiry.
    await redis_client.expire(key, 5)
    await store.save(thread_id, message_id="m2", trace_id="t2")
    refreshed_ttl = await redis_client.ttl(key)

    assert refreshed_ttl > 5


async def test_save_feedback_persists_true_and_false(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)

    await store.save_feedback("trace-up", score=True)
    await store.save_feedback("trace-down", score=False)

    batch = await store.get_feedback_batch(["trace-up", "trace-down"])
    assert batch == {"trace-up": True, "trace-down": False}


async def test_save_feedback_none_deletes_the_key(
    redis_client: aioredis.Redis,
) -> None:
    # A None score is "clear my feedback", not "store falsy" — it must DEL the key
    # so a later batch read omits the trace entirely (vs. reporting it as False).
    store = TraceStore(redis_client)
    await store.save_feedback("trace-x", score=True)
    assert await redis_client.exists("feedback:trace-x") == 1

    await store.save_feedback("trace-x", score=None)

    assert await redis_client.exists("feedback:trace-x") == 0
    assert await store.get_feedback_batch(["trace-x"]) == {}


async def test_save_feedback_none_on_absent_key_is_a_noop(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)

    await store.save_feedback("never-set", score=None)  # must not raise

    assert await store.get_feedback_batch(["never-set"]) == {}


async def test_save_feedback_arms_ttl(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)

    await store.save_feedback("trace-ttl", score=True)

    ttl = await redis_client.ttl("feedback:trace-ttl")
    assert 0 < ttl <= TraceStore.TTL


async def test_get_feedback_batch_empty_input_short_circuits(
    redis_client: aioredis.Redis,
) -> None:
    store = TraceStore(redis_client)

    assert await store.get_feedback_batch([]) == {}


async def test_get_feedback_batch_omits_missing_traces(
    redis_client: aioredis.Redis,
) -> None:
    # MGET returns None for absent keys; the store must drop those, not surface a
    # spurious entry — so a partially-rated batch yields only the rated traces.
    store = TraceStore(redis_client)
    await store.save_feedback("rated", score=True)

    batch = await store.get_feedback_batch(["rated", "unrated-1", "unrated-2"])

    assert batch == {"rated": True}
