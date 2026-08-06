"""Service layer for business logic."""

from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.domain.schemas import (
    AlertResponse,
    EventFilterParams,
    EventResponse,
    RuleResponse,
    SecurityEventIdentifiersResponse,
)
from siem_service.exceptions import ConflictError
from siem_service.pipeline.meta_emitter import MetaEmitter
from siem_service.repositories import AlertRepository, EventRepository, RuleRepository

logger = structlog.get_logger()


class EventService:
    """Service for event operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service.

        Args:
            session: SQLAlchemy async session
        """
        self.repository = EventRepository(session)

    async def list_events(
        self,
        filters: EventFilterParams,
    ) -> tuple[list[EventResponse], int]:
        """List events with filters and pagination.

        Args:
            filters: Filter and pagination parameters

        Returns:
            Tuple of (event_responses, total_count)
        """
        events, total = await self.repository.list_events(filters)
        responses = []
        for event in events:
            identifiers_data = event.identifiers or {}
            if isinstance(identifiers_data, dict):
                identifiers_obj = SecurityEventIdentifiersResponse(**identifiers_data)
            else:
                identifiers_obj = SecurityEventIdentifiersResponse()

            metadata = event.event_metadata or {}

            # Pydantic model with from_attributes=True will extract these values from the ORM instance
            response = EventResponse(
                event_id=event.event_id,
                event_type=event.event_type,
                severity=event.severity,
                event_timestamp=event.event_timestamp,
                ingested_at=event.ingested_at,
                identifiers=identifiers_obj,
                metadata=metadata,
            )
            responses.append(response)
        return responses, total


class AlertService:
    """Service for alert operations."""

    def __init__(
        self,
        session: AsyncSession,
        meta_emitter: MetaEmitter | None = None,
    ) -> None:
        """Initialize service."""
        self.session = session
        self.repository = AlertRepository(session)
        self.meta_emitter = meta_emitter

    async def list_alerts(
        self,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AlertResponse], int]:
        """List alerts with filters and pagination."""
        alerts, total = await self.repository.list_alerts(
            severity=severity,
            status=status,
            limit=limit,
            offset=offset,
        )

        responses = [
            AlertResponse.model_validate(alert, from_attributes=True)
            for alert in alerts
        ]
        return responses, total

    async def get_alert(self, alert_id: int) -> AlertResponse | None:
        """Get alert by ID."""
        alert = await self.repository.get_alert(alert_id)
        if not alert:
            return None

        return AlertResponse.model_validate(alert, from_attributes=True)

    async def acknowledge_alert(
        self,
        alert_id: int,
        user_id: str,
    ) -> AlertResponse | None:
        """Acknowledge an alert."""
        alert = await self.repository.get_alert(alert_id)
        if not alert:
            return None

        if alert.status == "resolved":
            # Cannot transition from resolved backwards
            logger.warning(
                "alert_already_resolved",
                alert_id=alert_id,
            )
            return AlertResponse.model_validate(alert, from_attributes=True)

        await self.repository.update_alert_status(alert_id, "acknowledged", user_id)

        # Emit meta-event
        if self.meta_emitter:
            await self.meta_emitter.emit(
                event_type="siem.alert.acknowledged",
                severity="info",
                user_id=user_id,
                metadata={
                    "alert_id": alert_id,
                    "rule_id": alert.rule_id,
                    "severity": alert.severity,
                },
            )

        alert = await self.repository.get_alert(alert_id)
        return AlertResponse.model_validate(alert, from_attributes=True)

    async def resolve_alert(
        self,
        alert_id: int,
        user_id: str,
    ) -> AlertResponse | None:
        """Resolve an alert."""
        alert = await self.repository.get_alert(alert_id)
        if not alert:
            return None

        # Allow idempotent resolve (resolved→resolved is OK)
        if alert.status != "resolved":
            await self.repository.update_alert_status(alert_id, "resolved", user_id)

            # Emit meta-event
            if self.meta_emitter:
                await self.meta_emitter.emit(
                    event_type="siem.alert.resolved",
                    severity="info",
                    user_id=user_id,
                    metadata={
                        "alert_id": alert_id,
                        "rule_id": alert.rule_id,
                        "severity": alert.severity,
                    },
                )

        alert = await self.repository.get_alert(alert_id)
        return AlertResponse.model_validate(alert, from_attributes=True)


class RuleService:
    """Service for correlation rule operations."""

    def __init__(
        self,
        session: AsyncSession,
        meta_emitter: MetaEmitter | None = None,
    ) -> None:
        """Initialize service."""
        self.session = session
        self.repository = RuleRepository(session)
        self.meta_emitter = meta_emitter

    async def list_rules(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RuleResponse], int]:
        """List correlation rules with pagination."""
        rules, total = await self.repository.list_rules(limit=limit, offset=offset)

        responses = [
            RuleResponse.model_validate(rule, from_attributes=True) for rule in rules
        ]
        return responses, total

    async def get_rule(self, rule_id: int) -> RuleResponse | None:
        """Get rule by ID."""
        rule = await self.repository.get_rule(rule_id)
        if not rule:
            return None

        return RuleResponse.model_validate(rule, from_attributes=True)

    async def create_rule(
        self,
        name: str,
        rule_type: str,
        config: dict[str, Any],
        severity: str = "warning",
        description: str | None = None,
        enabled: bool = True,
        user_id: str | None = None,
    ) -> RuleResponse:
        """Create a new correlation rule.

        Raises ConflictError if a rule with the same name already exists.
        """
        try:
            rule = await self.repository.create_rule(
                name=name,
                rule_type=rule_type,
                config=config,
                severity=severity,
                description=description,
                enabled=enabled,
            )
        except IntegrityError as e:
            raise ConflictError("Rule name already exists") from e

        # Emit meta-event
        if self.meta_emitter and user_id:
            await self.meta_emitter.emit(
                event_type="siem.rule.created",
                severity="info",
                user_id=user_id,
                metadata={
                    "rule_id": rule.id,
                    "rule_name": name,
                    "rule_type": rule_type,
                },
            )

        return RuleResponse.model_validate(rule, from_attributes=True)

    async def update_rule(
        self,
        rule_id: int,
        updates: dict[str, Any],
        user_id: str | None = None,
    ) -> RuleResponse | None:
        """Update a correlation rule."""
        rule = await self.repository.update_rule(rule_id, **updates)
        if not rule:
            return None

        # Emit meta-event
        if self.meta_emitter and user_id:
            await self.meta_emitter.emit(
                event_type="siem.rule.updated",
                severity="info",
                user_id=user_id,
                metadata={
                    "rule_id": rule_id,
                    "rule_name": rule.name,
                    "updates": updates,
                },
            )

        return RuleResponse.model_validate(rule, from_attributes=True)

    async def delete_rule(
        self,
        rule_id: int,
        user_id: str | None = None,
    ) -> bool:
        """Delete a correlation rule."""
        rule = await self.repository.get_rule(rule_id)
        if not rule:
            return False

        success = await self.repository.delete_rule(rule_id)

        # Emit meta-event
        if success and self.meta_emitter and user_id:
            await self.meta_emitter.emit(
                event_type="siem.rule.deleted",
                severity="info",
                user_id=user_id,
                metadata={
                    "rule_id": rule_id,
                    "rule_name": rule.name,
                },
            )

        return success
