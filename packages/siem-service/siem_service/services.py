"""Service layer for business logic."""

from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.repositories import EventRepository
from siem_service.schemas import (
    EventFilterParams,
    EventResponse,
    SecurityEventIdentifiersResponse,
)


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
            identifiers_data = event.identifiers or {}  # type: ignore[var-annotated]  # SQLAlchemy Column type
            if isinstance(identifiers_data, dict):
                identifiers_obj = SecurityEventIdentifiersResponse(**identifiers_data)
            else:
                identifiers_obj = SecurityEventIdentifiersResponse()

            metadata = event.event_metadata or {}  # type: ignore[var-annotated]  # SQLAlchemy Column type

            # Pydantic model with from_attributes=True will extract these values from the ORM instance
            response = EventResponse(
                event_id=event.event_id,  # type: ignore[arg-type]  # SQLAlchemy instrumented attribute
                event_type=event.event_type,  # type: ignore[arg-type]  # SQLAlchemy instrumented attribute
                severity=event.severity,  # type: ignore[arg-type]  # SQLAlchemy instrumented attribute
                event_timestamp=event.event_timestamp,  # type: ignore[arg-type]  # SQLAlchemy instrumented attribute
                ingested_at=event.ingested_at,  # type: ignore[arg-type]  # SQLAlchemy instrumented attribute
                identifiers=identifiers_obj,
                metadata=metadata,  # type: ignore[arg-type]  # SQLAlchemy Column[Any] type narrowing
            )
            responses.append(response)
        return responses, total
