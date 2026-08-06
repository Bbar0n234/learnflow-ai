"""RedisEventTransport + EventTransportHolder.

The holder is pure wiring (set/get). The transport's in-memory queue logic
(non-blocking enqueue, overflow-drops-newest, metrics, drain) is deterministic
and tested without Redis; the single external effect — ``xadd`` to the stream —
is asserted via a mocked client, since the call *is* the publish contract.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from app.security_pipeline.transport import EventTransportHolder, RedisEventTransport
from siem_contracts import (
    EventType,
    SecurityEvent,
    SecurityEventIdentifiers,
)

_EVENT_TYPE: EventType = "agent.guard.degraded"


def _event() -> SecurityEvent:
    return SecurityEvent(
        event_id=uuid.uuid4(),
        event_type=_EVENT_TYPE,
        severity="critical",
        timestamp=datetime.now(UTC),
        identifiers=SecurityEventIdentifiers(),
        metadata={},
    )


# --- holder ---------------------------------------------------------------


@pytest.mark.unit
def test_holder_returns_none_before_set() -> None:
    assert EventTransportHolder().get() is None


@pytest.mark.unit
def test_holder_returns_transport_after_set() -> None:
    holder = EventTransportHolder()
    transport = RedisEventTransport(AsyncMock())

    holder.set(transport)

    assert holder.get() is transport


# --- put_nowait queue semantics -------------------------------------------


@pytest.mark.unit
async def test_put_nowait_enqueues_and_counts() -> None:
    transport = RedisEventTransport(AsyncMock(), queue_maxsize=10)

    transport.put_nowait(_event())

    assert transport.get_metrics()["producer_published"] == 1


@pytest.mark.unit
async def test_put_nowait_drops_newest_on_overflow() -> None:
    transport = RedisEventTransport(AsyncMock(), queue_maxsize=1)

    transport.put_nowait(_event())  # fills the queue
    transport.put_nowait(_event())  # overflow -> dropped

    metrics = transport.get_metrics()
    assert metrics["producer_published"] == 1
    assert metrics["producer_drop_newest"] == 1


# --- publishing (external effect) -----------------------------------------


@pytest.mark.unit
async def test_publish_to_redis_calls_xadd_with_payload() -> None:
    redis_client = AsyncMock()
    transport = RedisEventTransport(redis_client)
    event = _event()

    await transport._publish_to_redis(event)

    redis_client.xadd.assert_awaited_once()
    _, kwargs = redis_client.xadd.call_args
    args = redis_client.xadd.call_args.args
    # Stream name first positional, payload second.
    assert args[0] == RedisEventTransport.STREAM_NAME
    payload = args[1]
    assert payload["event_type"] == _EVENT_TYPE
    assert payload["event_id"] == str(event.event_id)
    assert payload["severity"] == "critical"


@pytest.mark.unit
async def test_graceful_shutdown_drains_queue() -> None:
    redis_client = AsyncMock()
    transport = RedisEventTransport(redis_client, queue_maxsize=10)
    transport.put_nowait(_event())
    transport.put_nowait(_event())

    await transport.graceful_shutdown(timeout=5.0)

    assert redis_client.xadd.await_count == 2


@pytest.mark.unit
async def test_graceful_shutdown_counts_publish_errors() -> None:
    redis_client = AsyncMock()
    redis_client.xadd.side_effect = RuntimeError("redis down")
    transport = RedisEventTransport(redis_client, queue_maxsize=10)
    transport.put_nowait(_event())

    # A failing redis must not abort the drain; the error is counted, not raised.
    await transport.graceful_shutdown(timeout=5.0)

    assert transport.get_metrics()["producer_publish_errors"] == 1


# --- publisher loop (background drain) ------------------------------------


async def _wait_until(predicate: object, *, timeout: float = 2.0) -> None:
    """Poll an async-friendly condition without blocking the loop."""
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():  # type: ignore[operator]
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


@pytest.mark.unit
async def test_publisher_loop_publishes_queued_events_then_stops_on_cancel() -> None:
    redis_client = AsyncMock()
    transport = RedisEventTransport(redis_client, queue_maxsize=10)
    transport.put_nowait(_event())

    task = asyncio.create_task(transport.publisher_loop())
    await _wait_until(lambda: redis_client.xadd.await_count >= 1)
    task.cancel()
    await task  # CancelledError is handled internally -> clean stop

    assert redis_client.xadd.await_count == 1
    assert task.done()


@pytest.mark.unit
async def test_publisher_loop_counts_publish_errors_and_keeps_running() -> None:
    redis_client = AsyncMock()
    redis_client.xadd.side_effect = RuntimeError("redis down")
    transport = RedisEventTransport(redis_client, queue_maxsize=10)
    transport.put_nowait(_event())

    task = asyncio.create_task(transport.publisher_loop())
    await _wait_until(
        lambda: transport.get_metrics().get("producer_publish_errors", 0) >= 1
    )
    task.cancel()
    await task

    # The loop survived the publish failure (it counted, did not crash).
    assert transport.get_metrics()["producer_publish_errors"] == 1
