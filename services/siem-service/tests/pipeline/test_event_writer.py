"""EventWriter: the single insertion point, against a real Postgres.

Repository-shaped integration (testcontainers + transactional rollback): the
value here is the actual SQL — the ON CONFLICT DO NOTHING dedup and JSONB column
mapping — which a fake session could not exercise.
"""

from __future__ import annotations

import pytest
from siem_service.domain.models import SiemEvent
from siem_service.pipeline.event_writer import EventWriter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .fakes import make_event

pytestmark = pytest.mark.integration


async def test_write_new_event_returns_true_and_persists_fields(
    db_session: AsyncSession,
) -> None:
    event = make_event(
        event_type="auth.login.success",
        severity="info",
        identifiers={"ip": "198.51.100.7", "user_id": "u-1"},
        metadata={"reason": "ok", "attempt": 3},
    )

    is_new = await EventWriter(db_session).write(event)

    assert is_new is True
    stored = (
        await db_session.execute(
            select(SiemEvent).where(SiemEvent.event_id == event.event_id)
        )
    ).scalar_one()
    assert stored.event_type == "auth.login.success"
    assert stored.severity == "info"
    assert stored.identifiers == {"ip": "198.51.100.7", "user_id": "u-1"}
    # Pydantic field 'metadata' maps to the 'event_metadata' column.
    assert stored.event_metadata == {"reason": "ok", "attempt": 3}


async def test_write_duplicate_event_id_returns_false_and_keeps_single_row(
    db_session: AsyncSession,
) -> None:
    event = make_event()
    writer = EventWriter(db_session)

    first = await writer.write(event)
    second = await writer.write(event)

    assert first is True
    assert second is False
    count = (
        await db_session.execute(select(func.count()).select_from(SiemEvent))
    ).scalar_one()
    assert count == 1


async def test_write_duplicate_does_not_overwrite_first_payload(
    db_session: AsyncSession,
) -> None:
    # ON CONFLICT DO NOTHING: a second event reusing the id is ignored, the
    # original row is preserved (at-least-once dedup, not last-write-wins).
    event_id = make_event().event_id
    original = make_event(event_id=event_id, metadata={"v": "first"})
    collision = make_event(event_id=event_id, metadata={"v": "second"})
    writer = EventWriter(db_session)

    await writer.write(original)
    await writer.write(collision)

    stored = (
        await db_session.execute(
            select(SiemEvent).where(SiemEvent.event_id == event_id)
        )
    ).scalar_one()
    assert stored.event_metadata == {"v": "first"}
