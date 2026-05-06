"""Repository layer for database queries."""

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.models import CorrelationRule, SiemAlert, SiemEvent
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


class AlertRepository:
    """Repository for querying and managing alerts."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository."""
        self.session = session

    async def list_alerts(
        self,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SiemAlert], int]:
        """List alerts with filters and pagination.

        Args:
            severity: Filter by severity
            status: Filter by status
            limit: Items per page
            offset: Page offset

        Returns:
            Tuple of (alerts, total_count)
        """
        conditions = []

        if severity:
            conditions.append(SiemAlert.severity == severity)

        if status:
            conditions.append(SiemAlert.status == status)

        where_clause = and_(*conditions) if conditions else None

        # Get total count
        count_stmt = select(func.count()).select_from(SiemAlert)
        if where_clause is not None:
            count_stmt = count_stmt.where(where_clause)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Get paginated results
        stmt = select(SiemAlert).order_by(SiemAlert.created_at.desc())
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        alerts = list(result.scalars().all())

        return alerts, total

    async def get_alert(self, alert_id: int) -> SiemAlert | None:
        """Get alert by ID."""
        stmt = select(SiemAlert).where(SiemAlert.id == alert_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_alert_status(
        self,
        alert_id: int,
        status: str,
        user_id: str,
    ) -> SiemAlert | None:
        """Update alert status.

        Args:
            alert_id: Alert ID
            status: New status (acknowledged or resolved)
            user_id: User making the change

        Returns:
            Updated alert or None
        """
        alert = await self.get_alert(alert_id)
        if not alert:
            return None

        now = datetime.utcnow()

        if status == "acknowledged":
            alert.status = "acknowledged"  # type: ignore[assignment] # SQLAlchemy Column type
            alert.acknowledged_at = now  # type: ignore[assignment] # SQLAlchemy Column type
            alert.acknowledged_by = user_id  # type: ignore[assignment] # SQLAlchemy Column type
        elif status == "resolved":
            alert.status = "resolved"  # type: ignore[assignment] # SQLAlchemy Column type
            alert.resolved_at = now  # type: ignore[assignment] # SQLAlchemy Column type
            alert.resolved_by = user_id  # type: ignore[assignment] # SQLAlchemy Column type

        alert.updated_at = now  # type: ignore[assignment] # SQLAlchemy Column type
        self.session.add(alert)
        return alert


class RuleRepository:
    """Repository for managing correlation rules."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository."""
        self.session = session

    async def list_rules(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CorrelationRule], int]:
        """List rules with pagination.

        Args:
            limit: Items per page
            offset: Page offset

        Returns:
            Tuple of (rules, total_count)
        """
        # Get total count
        count_stmt = select(func.count()).select_from(CorrelationRule)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Get paginated results
        stmt = (
            select(CorrelationRule)
            .order_by(CorrelationRule.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        rules = list(result.scalars().all())

        return rules, total

    async def get_rule(self, rule_id: int) -> CorrelationRule | None:
        """Get rule by ID."""
        stmt = select(CorrelationRule).where(CorrelationRule.id == rule_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_rule_by_name(self, name: str) -> CorrelationRule | None:
        """Get rule by name."""
        stmt = select(CorrelationRule).where(CorrelationRule.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_rule(
        self,
        name: str,
        rule_type: str,
        config: dict[str, Any],
        severity: str = "warning",
        description: str | None = None,
        enabled: bool = True,
    ) -> CorrelationRule:
        """Create a new correlation rule."""
        rule = CorrelationRule(
            name=name,
            description=description,
            rule_type=rule_type,
            enabled=enabled,
            severity=severity,
            config=config,
        )
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def update_rule(
        self,
        rule_id: int,
        **kwargs: Any,
    ) -> CorrelationRule | None:
        """Update a correlation rule."""
        rule = await self.get_rule(rule_id)
        if not rule:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(rule, key):
                setattr(rule, key, value)

        rule.updated_at = datetime.utcnow()  # type: ignore[assignment] # SQLAlchemy Column type
        self.session.add(rule)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        """Delete a correlation rule."""
        rule = await self.get_rule(rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        return True
