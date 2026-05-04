"""REST API routes for SIEM service."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.db import get_session
from siem_service.schemas import EventFilterParams, PaginatedEventsResponse
from siem_service.services import EventService

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/events", response_model=PaginatedEventsResponse)
async def list_events(
    session: AsyncSession = Depends(get_session),  # noqa: B008 — FastAPI dependency injection
    event_type: str | None = Query(None, description="Filter by event type"),  # noqa: B008
    severity: str | None = Query(None, description="Filter by severity"),  # noqa: B008
    from_timestamp: str | None = Query(None, alias="from", description="Start time"),  # noqa: B008
    to_timestamp: str | None = Query(None, alias="to", description="End time"),  # noqa: B008
    limit: int = Query(50, ge=1, le=200, description="Items per page"),  # noqa: B008
    offset: int = Query(0, ge=0, description="Page offset"),  # noqa: B008
) -> PaginatedEventsResponse:
    """List security events with filtering and pagination.

    Args:
        event_type: Filter by event type
        severity: Filter by severity (info, warning, critical)
        from_timestamp: Start timestamp (ISO 8601)
        to_timestamp: End timestamp (ISO 8601)
        limit: Items per page (max 200)
        offset: Page offset
        session: Database session

    Returns:
        Paginated list of events
    """
    from datetime import datetime

    # Parse timestamps if provided
    from_dt = None
    to_dt = None

    try:
        if from_timestamp:
            from_dt = datetime.fromisoformat(from_timestamp.replace("Z", "+00:00"))
        if to_timestamp:
            to_dt = datetime.fromisoformat(to_timestamp.replace("Z", "+00:00"))
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid timestamp format: {e}"
        ) from e

    # Create filter params
    filters = EventFilterParams(
        event_type=event_type,
        severity=severity,
        from_timestamp=from_dt,
        to_timestamp=to_dt,
        limit=limit,
        offset=offset,
    )

    # Get events from service
    service = EventService(session)
    events, total = await service.list_events(filters)

    return PaginatedEventsResponse(
        items=events,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "ok"}
