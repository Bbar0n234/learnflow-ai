"""Subscriber ingest behavior: validate → write → ack, and the drop barriers.

Sociable-unit on a fake Redis (the painful external boundary) with the *real*
Postgres under the write path (ingest is repository-shaped — see testing.md
§ SIEM event parsing / ingest). The subscriber's public surface is ``run()``;
we drive one scripted batch through it and assert observable effects: rows in the
DB, XACKs recorded on the fake, and the metrics counter.

The fake's ``run`` loop stops by raising ``CancelledError`` once its scripted
messages are exhausted — that is the public way to end the otherwise-infinite
loop; ``_drain`` swallows it so the test can assert post-conditions.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from uuid import uuid4

import pytest
from siem_contracts import SecurityEvent
from siem_service.domain.models import SiemEvent
from siem_service.pipeline.subscriber import Subscriber
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from .fakes import (
    CountingSessionFactory,
    FailingSessionFactory,
    FakeStreamRedis,
    event_message,
    make_event,
    make_settings,
    make_subscriber,
    producer_envelope,
    raw_message,
)

pytestmark = pytest.mark.integration


async def _drain(subscriber: Subscriber) -> None:
    """Run the subscriber until its scripted stream is exhausted."""
    with contextlib.suppress(asyncio.CancelledError):
        await subscriber.run()


def _session_factory(session: AsyncSession) -> CountingSessionFactory:
    return CountingSessionFactory(session)


async def _count_events(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(SiemEvent))
    return int(result.scalar_one())


async def test_subscriber_valid_event_is_written_and_acked(
    db_session: AsyncSession,
) -> None:
    event = make_event()
    redis = FakeStreamRedis([event_message("1-0", event)])
    factory = _session_factory(db_session)
    subscriber = make_subscriber(redis, factory, make_settings())

    await _drain(subscriber)

    stored = (
        await db_session.execute(
            select(SiemEvent).where(SiemEvent.event_id == event.event_id)
        )
    ).scalar_one()
    assert stored.event_type == event.event_type
    assert stored.severity == event.severity
    assert redis.acked == ["1-0"]
    assert subscriber.get_metrics()["siem_events_ingested"] == 1


async def test_subscriber_persists_producer_identifiers_excluding_none(
    db_session: AsyncSession,
) -> None:
    # Producer serializes identifiers with exclude_none; only set keys land in JSONB.
    event = make_event(identifiers={"ip": "203.0.113.5", "user_id": "u-42"})
    redis = FakeStreamRedis([event_message("1-0", event)])
    subscriber = make_subscriber(redis, _session_factory(db_session), make_settings())

    await _drain(subscriber)

    stored = (
        await db_session.execute(
            select(SiemEvent).where(SiemEvent.event_id == event.event_id)
        )
    ).scalar_one()
    assert stored.identifiers == {"ip": "203.0.113.5", "user_id": "u-42"}
    assert "thread_id" not in stored.identifiers


async def test_subscriber_duplicate_event_id_is_deduplicated_and_acked(
    db_session: AsyncSession,
) -> None:
    event = make_event()
    redis = FakeStreamRedis([event_message("1-0", event), event_message("2-0", event)])
    subscriber = make_subscriber(redis, _session_factory(db_session), make_settings())

    await _drain(subscriber)

    assert await _count_events(db_session) == 1
    # Both deliveries are acked (idempotent ingest), one counted as duplicate.
    assert redis.acked == ["1-0", "2-0"]
    metrics = subscriber.get_metrics()
    # Metric semantics (intentional): `ingested` counts every successfully
    # processed delivery, dedup included; `duplicate` is the subset that hit
    # ON CONFLICT DO NOTHING. So unique rows == ingested - duplicate, which must
    # reconcile with the single DB row. A dashboard reading `ingested` as "unique
    # events" would double-count here — this asserts the documented relationship.
    assert metrics["siem_events_ingested"] == 2
    assert metrics["siem_events_duplicate"] == 1
    assert metrics["siem_events_ingested"] - metrics[
        "siem_events_duplicate"
    ] == await _count_events(db_session)


@pytest.mark.parametrize(
    ("bad_payload", "reason"),
    [
        (
            json.dumps(
                {
                    "event_id": str(uuid4()),
                    "event_type": "auth.login.failed",
                    "severity": "fatal",  # not in info|warning|critical
                    "timestamp": "2026-06-22T00:00:00Z",
                }
            ),
            "invalid_severity",
        ),
        (
            json.dumps(
                {
                    "event_id": str(uuid4()),
                    "event_type": "totally.unknown.type",  # not in vocabulary Literal
                    "severity": "info",
                    "timestamp": "2026-06-22T00:00:00Z",
                }
            ),
            "unknown_event_type",
        ),
        (
            json.dumps(
                {"event_type": "auth.login.failed", "severity": "info"}
            ),  # missing event_id + timestamp
            "missing_required_fields",
        ),
    ],
    ids=["invalid_severity", "unknown_event_type", "missing_required_fields"],
)
async def test_subscriber_poison_event_is_dropped_acked_without_db_write(
    db_session: AsyncSession, bad_payload: str, reason: str
) -> None:
    redis = FakeStreamRedis([raw_message("1-0", bad_payload)])
    factory = _session_factory(db_session)
    subscriber = make_subscriber(redis, factory, make_settings())

    await _drain(subscriber)

    # Poison (ValidationError) → acked once, never opened a write session.
    assert redis.acked == ["1-0"], reason
    assert factory.calls == 0
    assert subscriber.get_metrics()["siem_events_invalid"] == 1
    assert await _count_events(db_session) == 0


async def test_subscriber_terminal_drop_after_max_delivery_attempts(
    db_session: AsyncSession,
) -> None:
    event = make_event()
    settings = make_settings()
    # Fake reports a delivery count beyond the bound → terminal drop before parse.
    redis = FakeStreamRedis(
        [event_message("1-0", event)],
        times_delivered=settings.max_delivery_attempts + 1,
    )
    factory = _session_factory(db_session)
    subscriber = make_subscriber(redis, factory, settings)

    await _drain(subscriber)

    assert redis.acked == ["1-0"]
    assert factory.calls == 0  # dropped before any DB work
    assert subscriber.get_metrics()["siem_events_failed_terminal"] == 1
    assert await _count_events(db_session) == 0


@pytest.mark.parametrize(
    "factory",
    [
        FailingSessionFactory(
            OperationalError("INSERT", {}, Exception("connection lost"))
        ),
        # Raw connect-time failure asyncpg raises when the DB is fully down; it is
        # not wrapped into SQLAlchemy's OperationalError (stand finding F-SIEM-T4.13).
        FailingSessionFactory(ConnectionRefusedError("db down"), on_enter=True),
    ],
    ids=["execute_operational_error", "connect_refused_on_open"],
)
async def test_subscriber_transient_db_error_is_not_acked(
    factory: FailingSessionFactory,
) -> None:
    event = make_event()
    redis = FakeStreamRedis([event_message("1-0", event)])
    subscriber = make_subscriber(redis, factory, make_settings())

    await _drain(subscriber)

    # Transient infra failure → message stays in PEL (no XACK) for re-delivery.
    assert redis.acked == []
    assert factory.calls == 1
    assert subscriber.get_metrics()["siem_events_transient"] == 1


async def test_subscriber_malformed_non_json_payload_is_poison_dropped(
    db_session: AsyncSession,
) -> None:
    # A payload that is not even valid JSON fails json.loads. It must be treated
    # as poison — symmetric with schema-invalid JSON — i.e. drop + XACK + the
    # siem_events_invalid metric, never opening a write session. Re-raising it to
    # the supervisor barrier (the old behavior) would crash-loop the task until
    # the terminal-drop counter eventually evicts it (DoS-flavored).
    redis = FakeStreamRedis([raw_message("1-0", "not-json{")])
    factory = _session_factory(db_session)
    subscriber = make_subscriber(redis, factory, make_settings())

    await _drain(subscriber)

    assert redis.acked == ["1-0"]
    assert factory.calls == 0
    assert subscriber.get_metrics()["siem_events_invalid"] == 1
    assert await _count_events(db_session) == 0


async def test_subscriber_consumes_producer_serialized_envelope(
    db_session: AsyncSession,
) -> None:
    # Build the payload exactly as the emitter's transport does and prove the
    # consumer parses that wire format end to end.
    event = make_event(event_type="agent.guard.input.classifier_injection")
    envelope = producer_envelope(event)
    assert SecurityEvent.model_validate_json(envelope["data"]) == event  # producer side
    redis = FakeStreamRedis([("9-0", envelope)])
    subscriber = make_subscriber(redis, _session_factory(db_session), make_settings())

    await _drain(subscriber)

    stored = (
        await db_session.execute(
            select(SiemEvent).where(SiemEvent.event_id == event.event_id)
        )
    ).scalar_one()
    assert stored.event_type == "agent.guard.input.classifier_injection"
    assert redis.acked == ["9-0"]
