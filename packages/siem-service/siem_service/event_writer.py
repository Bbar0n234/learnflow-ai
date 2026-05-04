"""Single point of insertion for security events into database."""

import structlog
from siem_contracts import SecurityEvent
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.models import SiemEvent

logger = structlog.get_logger()


class EventWriter:
    """Writes security events to database with deduplication via ON CONFLICT."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize event writer with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def write(self, event: SecurityEvent) -> bool:
        """Write event to database with idempotent deduplication.

        On duplicate event_id, performs no-op (ON CONFLICT DO NOTHING).

        Args:
            event: SecurityEvent to write

        Returns:
            True if new event was inserted, False if duplicate was ignored
        """
        stmt = pg_insert(SiemEvent).values(
            event_id=event.event_id,
            event_type=event.event_type,
            severity=event.severity,
            event_timestamp=event.timestamp,
            identifiers=event.identifiers.model_dump(mode="json", exclude_none=True),
            event_metadata=event.metadata,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])

        try:
            result = await self.session.execute(stmt)
            await self.session.commit()
            # rowcount is available on CursorResult but mypy stubs incomplete for it
            row_count: int = result.rowcount or 0  # type: ignore[attr-defined]  # SQLAlchemy Result.rowcount
            if row_count < 1:
                logger.debug(
                    "event already exists (duplicate event_id)",
                    event_id=str(event.event_id),
                )
                return False
            logger.debug(
                "event written to database",
                event_id=str(event.event_id),
                event_type=event.event_type,
            )
            return True
        except Exception:
            await self.session.rollback()
            logger.error(
                "failed to write event",
                event_id=str(event.event_id),
                exc_info=True,
            )
            raise
