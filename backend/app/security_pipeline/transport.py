"""Security event transport via Redis Streams."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import cast

import redis.asyncio as redis
import structlog
from siem_contracts import SecurityEvent

logger = structlog.get_logger()


class EventTransport:
    """Interface for security event publishing."""

    async def publish(self, event: SecurityEvent) -> None:
        """Publish a security event."""
        raise NotImplementedError


class RedisEventTransport(EventTransport):
    """Redis Streams-based event transport."""

    STREAM_NAME = "security.events"
    MAXLEN = 100_000

    def __init__(
        self,
        redis_client: redis.Redis,
        queue_maxsize: int = 1000,
    ) -> None:
        """Initialize Redis transport.

        Args:
            redis_client: Redis client instance
            queue_maxsize: Maximum size of in-memory queue before dropping events
        """
        self._redis = redis_client
        self._queue: asyncio.Queue[SecurityEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._metrics: dict[str, int] = defaultdict(int)
        self._publisher_task: asyncio.Task[None] | None = None

    def put_nowait(self, event: SecurityEvent) -> None:
        """Non-blocking publish to bounded queue.

        On queue overflow, drops newest event and increments drop counter.
        Called from synchronous context (structlog processor).

        Args:
            event: Security event to publish
        """
        try:
            self._queue.put_nowait(event)
            self._metrics["producer_published"] += 1
        except asyncio.QueueFull:
            self._metrics["producer_drop_newest"] += 1
            logger.warning(
                "security event queue full, dropping newest",
                event_type=event.event_type,
                event_id=str(event.event_id),
            )

    async def publisher_loop(self) -> None:
        """Async background task: read from queue and publish to Redis Stream.

        This should be started in lifespan startup and runs until shutdown.
        Handles connection errors with logging and continues.
        """
        logger.info("security event publisher loop starting")
        while True:
            try:
                event = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )  # Check periodically for graceful shutdown
                try:
                    await self._publish_to_redis(event)
                except Exception:
                    self._metrics["producer_publish_errors"] += 1
                    logger.error(
                        "failed to publish event to redis",
                        event_id=str(event.event_id),
                        exc_info=True,
                    )
            except TimeoutError:
                # Timeout is normal, allows graceful shutdown checks
                continue
            except asyncio.CancelledError:
                # Shutdown signal
                logger.info("security event publisher loop cancelled")
                break

    async def _publish_to_redis(self, event: SecurityEvent) -> None:
        """Publish single event to Redis Stream."""
        payload: dict[str, str] = {
            "data": event.model_dump_json(),
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "severity": event.severity,
        }
        await self._redis.xadd(
            self.STREAM_NAME,
            cast(dict[str | bytes | int | float, str | bytes | int | float], payload),
            maxlen=self.MAXLEN,
            approximate=True,
        )

    async def graceful_shutdown(self, timeout: float = 5.0) -> None:
        """Gracefully drain queue on shutdown.

        Args:
            timeout: Maximum time to wait for queue to drain
        """
        logger.info("security event publisher graceful shutdown", timeout=timeout)
        deadline = asyncio.get_event_loop().time() + timeout
        while not self._queue.empty():
            if asyncio.get_event_loop().time() > deadline:
                remaining = self._queue.qsize()
                logger.warning(
                    "security event publisher shutdown timeout",
                    remaining_events=remaining,
                )
                break
            try:
                event = self._queue.get_nowait()
                await self._publish_to_redis(event)
            except asyncio.QueueEmpty:
                break
            except Exception:
                self._metrics["producer_publish_errors"] += 1
                logger.error(
                    "failed to publish event during shutdown",
                    exc_info=True,
                )

    def get_metrics(self) -> dict[str, int]:
        """Get current metrics dictionary."""
        return dict(self._metrics)


class EventTransportHolder:
    """Container for the active event transport.

    The structlog processor needs to publish events but is configured before
    the transport exists (logging starts during lifespan, Redis connects later).
    The holder is created up front, passed into the processor factory, and
    populated once the transport is ready. No module-level state, no singletons:
    the holder is owned by app.state and captured by closure in the processor.
    """

    def __init__(self) -> None:
        self._transport: RedisEventTransport | None = None

    def set(self, transport: RedisEventTransport) -> None:
        self._transport = transport

    def get(self) -> RedisEventTransport | None:
        return self._transport
