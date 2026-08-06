"""Local fakes for the ingest-pipeline tests (S8 scope).

Redis is the painful external boundary of the subscriber; we fake it in-memory so
the ingest logic (validate → write → ack, poison drop, terminal drop) runs
deterministically without a live Redis. The DB stays real (see test modules using
``db_session``) because that is the layer the integration tests exist to exercise.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import redis.asyncio as redis
from siem_contracts import SecurityEvent
from siem_service.config import Settings
from siem_service.pipeline.subscriber import Subscriber
from sqlalchemy.ext.asyncio import AsyncSession

_STREAM = "security.events"

# A message as the subscriber consumes it: (message_id, {"data": <json>}).
Message = tuple[str, dict[str, Any]]


def make_settings() -> Settings:
    """Settings for the subscriber under test (SIEM_JWT_SECRET set by conftest)."""
    return Settings()


def make_subscriber(
    redis_client: object, session_factory: object, settings: Settings
) -> Subscriber:
    """Construct a Subscriber over a duck-typed fake Redis.

    ``Subscriber`` types ``redis_client`` as the concrete ``redis.Redis`` rather
    than a Protocol, so the in-memory fake is bridged with a single ``cast`` here
    (duck-typing per testing.md § Дубли) instead of scattering ignores per call.
    """
    return Subscriber(cast(redis.Redis, redis_client), session_factory, settings)


def make_event(
    event_type: str = "auth.login.failed",
    *,
    event_id: UUID | None = None,
    severity: str = "warning",
    identifiers: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SecurityEvent:
    """Build a valid SecurityEvent for ingest tests."""
    return SecurityEvent.model_validate(
        {
            "event_id": event_id or uuid4(),
            "event_type": event_type,
            "severity": severity,
            "timestamp": datetime.now(UTC),
            "identifiers": identifiers or {"ip": "192.0.2.1", "request_id": "req-1"},
            "metadata": metadata or {"reason": "invalid_credentials"},
        }
    )


def producer_envelope(event: SecurityEvent) -> dict[str, Any]:
    """Replicate the producer's Redis-Stream payload (transport ``_publish_to_redis``).

    The emitter serializes the event into a ``{"data": <model_dump_json>}`` envelope
    plus a few flat fields; the consumer only reads ``data``. Using the producer's
    exact serialization here is what makes this a cross-side wire-format check.
    """
    return {
        "data": event.model_dump_json(),
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "severity": event.severity,
    }


def raw_message(message_id: str, data: str) -> Message:
    """A stream message carrying an arbitrary (possibly malformed) ``data`` string."""
    return (message_id, {"data": data})


def event_message(message_id: str, event: SecurityEvent) -> Message:
    """A stream message carrying a producer-serialized SecurityEvent."""
    return (message_id, producer_envelope(event))


class FakeStreamRedis:
    """In-memory stand-in for the Redis Streams client used by ``Subscriber``.

    Delivers a scripted batch of new messages exactly once, then raises
    ``CancelledError`` from the next ``>`` read so the subscriber's ``run`` loop
    exits cleanly (the public way to stop the otherwise-infinite loop). Records
    every ``XACK`` so tests can assert acknowledgement as an observable effect.
    """

    def __init__(self, messages: list[Message], *, times_delivered: int = 1) -> None:
        self._new: list[Message] = list(messages)
        self._times_delivered = times_delivered
        self.acked: list[str] = []

    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int | None = None,
    ) -> list[tuple[str, list[Message]]]:
        last_id = next(iter(streams.values()))
        if last_id == "0":
            # Pending read on a fresh group: nothing pending.
            return []
        if self._new:
            batch = self._new
            self._new = []
            return [(_STREAM, batch)]
        # No more new messages: stop the loop via the cancellation barrier.
        raise asyncio.CancelledError

    async def xpending_range(
        self,
        name: str,
        groupname: str,
        min: str,
        max: str,
        count: int,
    ) -> list[dict[str, Any]]:
        return [{"message_id": min, "times_delivered": self._times_delivered}]

    async def xack(self, stream: str, group: str, message_id: str) -> int:
        self.acked.append(message_id)
        return 1


class CountingSessionFactory:
    """Async-session factory that hands out the test's transactional session.

    Counts how many times the subscriber opened a write session so tests can
    assert that poison/terminal messages are dropped *before* any DB work.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        return self._ctx()

    @asynccontextmanager
    async def _ctx(self) -> AsyncIterator[AsyncSession]:
        # Do not close: the db_session fixture owns the transactional rollback.
        yield self._session


class _RaisingSession:
    """Minimal async-session stand-in whose ``execute`` raises a given error.

    Stands in for a DB connection that drops mid-statement: ``EventWriter.write``
    calls ``execute`` → error → ``rollback`` → re-raise. Lets the transient-error
    path be exercised without a live-but-broken Postgres.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.rolled_back = False

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        raise self._exc

    async def commit(self) -> None:  # pragma: no cover - never reached
        return None

    async def rollback(self) -> None:
        self.rolled_back = True


class FailingSessionFactory:
    """Session factory that simulates a DB-infra failure on the write path.

    Two failure shapes the subscriber must treat as *transient* (no XACK, keep in
    PEL):
    - ``on_enter=False`` (default): the session opens, but ``execute`` raises
      ``exc`` (SQLAlchemy-wrapped ``OperationalError``/``DBAPIError`` — a live
      connection dropping mid-statement).
    - ``on_enter=True``: opening the session itself raises ``exc`` (raw
      connect-time ``ConnectionRefusedError`` asyncpg raises when the DB is fully
      down — not wrapped by SQLAlchemy).

    Counts opens so callers can assert the write path was attempted.
    """

    def __init__(self, exc: BaseException, *, on_enter: bool = False) -> None:
        self._exc = exc
        self._on_enter = on_enter
        self.calls = 0
        self.session: _RaisingSession | None = None

    def __call__(self) -> Any:
        self.calls += 1
        return self._ctx()

    @asynccontextmanager
    async def _ctx(self) -> AsyncIterator[Any]:
        if self._on_enter:
            raise self._exc
        self.session = _RaisingSession(self._exc)
        yield self.session
