"""Alert deduplication logic with open-alert policy."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from siem_service.config import get_settings
from siem_service.domain.models import SiemAlert

logger = structlog.get_logger()


class AlertCandidate:
    """Alert candidate from correlation engine."""

    def __init__(
        self,
        rule_id: int,
        severity: str,
        group_key: str | None,
        first_event_id: UUID,
        latest_event_id: UUID,
    ) -> None:
        """Initialize alert candidate."""
        self.rule_id = rule_id
        self.severity = severity
        self.group_key = group_key
        self.first_event_id = first_event_id
        self.latest_event_id = latest_event_id


class AlertDeduper:
    """Handles alert deduplication with open-alert policy."""

    @staticmethod
    async def dedupe(
        candidate: AlertCandidate,
        session: AsyncSession,
    ) -> SiemAlert | None:
        """
        Apply open-alert policy: find existing new alert for (rule_id, group_key).

        Returns:
            SiemAlert instance if alert was found and updated, or newly created alert.
        """
        now = datetime.now(UTC)
        age_threshold = now - timedelta(
            seconds=get_settings().alert_open_window_seconds
        )

        # Find open alert (new status) for this rule and group_key, created within 24h
        query = select(SiemAlert).where(
            SiemAlert.rule_id == candidate.rule_id,
            SiemAlert.status == "new",
            SiemAlert.created_at >= age_threshold,
        )

        # If group_key is provided, match it exactly
        # If group_key is NULL (for Aggregate rules), match NULL
        if candidate.group_key is not None:
            query = query.where(SiemAlert.group_key == candidate.group_key)
        else:
            query = query.where(SiemAlert.group_key.is_(None))

        result = await session.execute(query)
        existing_alert = result.scalar_one_or_none()

        if existing_alert:
            # Append to existing alert
            existing_alert.matched_events_count += 1  # type: ignore[assignment] # SQLAlchemy Column type
            existing_alert.latest_event_id = candidate.latest_event_id  # type: ignore[assignment] # SQLAlchemy Column type
            existing_alert.updated_at = now  # type: ignore[assignment] # SQLAlchemy Column type
            session.add(existing_alert)
            logger.info(
                "alert_appended",
                rule_id=candidate.rule_id,
                alert_id=existing_alert.id,
                group_key=candidate.group_key,
            )
            return existing_alert

        # Create new alert
        new_alert = SiemAlert(
            rule_id=candidate.rule_id,
            severity=candidate.severity,
            status="new",
            group_key=candidate.group_key,
            matched_events_count=1,
            first_event_id=candidate.first_event_id,
            latest_event_id=candidate.latest_event_id,
        )
        session.add(new_alert)
        logger.info(
            "alert_created",
            rule_id=candidate.rule_id,
            group_key=candidate.group_key,
            severity=candidate.severity,
        )
        return new_alert
