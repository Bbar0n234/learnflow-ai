"""Alert deduplication logic with open-alert policy."""

from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.domain.models import SiemAlert

logger = structlog.get_logger()


@dataclass
class AlertCandidate:
    """Alert candidate from correlation engine."""

    rule_id: int
    severity: str
    group_key: str | None
    first_event_id: UUID
    latest_event_id: UUID


class AlertDeduper:
    """Handles alert deduplication with open-alert policy."""

    @staticmethod
    async def dedupe(
        candidate: AlertCandidate,
        session: AsyncSession,
    ) -> SiemAlert:
        """
        Apply open-alert policy: append to the open (`new`) alert for
        (rule_id, group_key) or create a fresh one — in a single atomic upsert.

        Гонка реплик исключена: ON CONFLICT опирается на частичный уникальный
        индекс uq_siem_alerts_open_alert. Протухание открытых алертов — забота
        CorrelationEngine (перевод в `expired` до оценки правил).

        Returns:
            SiemAlert instance: created or updated open alert.
        """
        stmt = (
            pg_insert(SiemAlert)
            .values(
                rule_id=candidate.rule_id,
                severity=candidate.severity,
                status="new",
                group_key=candidate.group_key,
                matched_events_count=1,
                first_event_id=candidate.first_event_id,
                latest_event_id=candidate.latest_event_id,
            )
            .on_conflict_do_update(
                index_elements=["rule_id", "group_key"],
                index_where=text("status = 'new'"),
                set_={
                    "matched_events_count": SiemAlert.matched_events_count + 1,
                    "latest_event_id": candidate.latest_event_id,
                    "updated_at": func.now(),
                },
            )
            .returning(SiemAlert)
        )
        result = await session.execute(stmt)
        alert = result.scalars().one()

        if alert.matched_events_count > 1:
            logger.info(
                "alert_appended",
                rule_id=candidate.rule_id,
                alert_id=alert.id,
                group_key=candidate.group_key,
            )
        else:
            logger.info(
                "alert_created",
                rule_id=candidate.rule_id,
                alert_id=alert.id,
                group_key=candidate.group_key,
                severity=candidate.severity,
            )
        return alert
