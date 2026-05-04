"""Repository layer for database queries."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.models import SiemEvent
from siem_service.schemas import EventFilterParams


class EventRepository:
    """Repository for querying security events."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def list_events(
        self,
        filters: EventFilterParams,
    ) -> tuple[list[SiemEvent], int]:
        """List events with filters and pagination.

        Args:
            filters: Filter and pagination parameters

        Returns:
            Tuple of (events, total_count)
        """
        # Build WHERE clause
        conditions = []

        if filters.event_type:
            conditions.append(SiemEvent.event_type == filters.event_type)

        if filters.severity:
            conditions.append(SiemEvent.severity == filters.severity)

        if filters.from_timestamp:
            conditions.append(SiemEvent.event_timestamp >= filters.from_timestamp)

        if filters.to_timestamp:
            conditions.append(SiemEvent.event_timestamp <= filters.to_timestamp)

        where_clause = and_(*conditions) if conditions else None

        # Get total count
        count_stmt = select(func.count()).select_from(SiemEvent)
        if where_clause is not None:
            count_stmt = count_stmt.where(where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Get paginated results
        stmt = select(SiemEvent).order_by(SiemEvent.ingested_at.desc())
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = stmt.limit(filters.limit).offset(filters.offset)

        result = await self.session.execute(stmt)
        events = list(result.scalars().all())

        return events, total
