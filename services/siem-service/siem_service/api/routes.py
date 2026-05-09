"""REST API routes for SIEM service."""

from datetime import datetime
from typing import Annotated

import redis.asyncio as redis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from siem_service.domain.schemas import (
    AlertPatchRequest,
    AlertResponse,
    EventFilterParams,
    PaginatedAlertsResponse,
    PaginatedEventsResponse,
    PaginatedRulesResponse,
    RuleCreateRequest,
    RuleResponse,
    RuleUpdateRequest,
)
from siem_service.infra.auth import require_admin
from siem_service.infra.db import get_session
from siem_service.pipeline.meta_emitter import get_meta_emitter
from siem_service.services import AlertService, EventService, RuleService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/security", tags=["security"])


async def get_redis_from_request(request: Request) -> redis.Redis:
    """Get Redis client from app state.

    This dependency retrieves the async Redis client initialized in lifespan.
    """
    if not hasattr(request.app.state, "redis"):
        raise RuntimeError("Redis client not initialized in app state")
    return request.app.state.redis


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


# ============================================================================
# Alerts endpoints (admin-only)
# ============================================================================


@router.get("/alerts", response_model=PaginatedAlertsResponse)
async def list_alerts(
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    severity: str | None = Query(None, description="Filter by severity"),  # noqa: B008
    status: str | None = Query(None, description="Filter by status"),  # noqa: B008
    limit: int = Query(50, ge=1, le=200, description="Items per page"),  # noqa: B008
    offset: int = Query(0, ge=0, description="Page offset"),  # noqa: B008
) -> PaginatedAlertsResponse:
    """List security alerts with filtering and pagination (admin-only).

    Args:
        severity: Filter by severity (info, warning, critical)
        status: Filter by status (new, acknowledged, resolved)
        limit: Items per page (max 200)
        offset: Page offset
        session: Database session
        admin_payload: Admin JWT payload (required)

    Returns:
        Paginated list of alerts
    """
    service = AlertService(session)
    alerts, total = await service.list_alerts(
        severity=severity,
        status=status,
        limit=limit,
        offset=offset,
    )

    return PaginatedAlertsResponse(
        items=alerts,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> AlertResponse:
    """Get alert details (admin-only).

    Args:
        alert_id: Alert ID
        session: Database session
        admin_payload: Admin JWT payload (required)

    Returns:
        Alert details
    """
    service = AlertService(session)
    alert = await service.get_alert(alert_id)

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    return alert


@router.patch("/alerts/{alert_id}", response_model=AlertResponse)
async def patch_alert(
    alert_id: int,
    request: AlertPatchRequest,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    redis_client: redis.Redis = Depends(get_redis_from_request),  # noqa: B008
) -> AlertResponse:
    """Update alert status (admin-only).

    Args:
        alert_id: Alert ID
        request: Patch request (status: acknowledged | resolved)
        session: Database session
        admin_payload: Admin JWT payload (required)
        redis_client: Async Redis client (injected from app state)

    Returns:
        Updated alert
    """
    if request.status not in ("acknowledged", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'acknowledged' or 'resolved'",
        )

    user_id = admin_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'sub' claim in token",
        )

    meta_emitter = get_meta_emitter(redis_client)

    service = AlertService(session, meta_emitter=meta_emitter)

    if request.status == "acknowledged":
        alert = await service.acknowledge_alert(alert_id, str(user_id))
    else:
        alert = await service.resolve_alert(alert_id, str(user_id))

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found"
        )

    await session.commit()
    return alert


# ============================================================================
# Rules endpoints (admin-only)
# ============================================================================


@router.get("/rules", response_model=PaginatedRulesResponse)
async def list_rules(
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    limit: int = Query(50, ge=1, le=200, description="Items per page"),  # noqa: B008
    offset: int = Query(0, ge=0, description="Page offset"),  # noqa: B008
) -> PaginatedRulesResponse:
    """List correlation rules (admin-only).

    Args:
        limit: Items per page
        offset: Page offset
        session: Database session
        admin_payload: Admin JWT payload (required)

    Returns:
        Paginated list of rules
    """
    service = RuleService(session)
    rules, total = await service.list_rules(limit=limit, offset=offset)

    return PaginatedRulesResponse(
        items=rules,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/rules/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: int,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> RuleResponse:
    """Get rule details (admin-only).

    Args:
        rule_id: Rule ID
        session: Database session
        admin_payload: Admin JWT payload (required)

    Returns:
        Rule details
    """
    service = RuleService(session)
    rule = await service.get_rule(rule_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )

    return rule


@router.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: RuleCreateRequest,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    redis_client: redis.Redis = Depends(get_redis_from_request),  # noqa: B008
) -> RuleResponse:
    """Create a new correlation rule (admin-only).

    Args:
        request: Rule creation request
        session: Database session
        admin_payload: Admin JWT payload (required)
        redis_client: Async Redis client (injected from app state)

    Returns:
        Created rule
    """
    user_id = admin_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'sub' claim in token",
        )

    meta_emitter = get_meta_emitter(redis_client)

    service = RuleService(session, meta_emitter=meta_emitter)
    rule = await service.create_rule(
        name=request.name,
        rule_type=request.rule_type,
        config=request.config,
        severity=request.severity,
        description=request.description,
        enabled=request.enabled,
        user_id=str(user_id),
    )

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create rule",
        )

    await session.commit()
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    request: RuleUpdateRequest,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    redis_client: redis.Redis = Depends(get_redis_from_request),  # noqa: B008
) -> RuleResponse:
    """Update a correlation rule (admin-only).

    Args:
        rule_id: Rule ID
        request: Rule update request
        session: Database session
        admin_payload: Admin JWT payload (required)
        redis_client: Async Redis client (injected from app state)

    Returns:
        Updated rule
    """
    user_id = admin_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'sub' claim in token",
        )

    meta_emitter = get_meta_emitter(redis_client)

    service = RuleService(session, meta_emitter=meta_emitter)

    # Filter out None values
    updates = {k: v for k, v in request.model_dump().items() if v is not None}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    rule = await service.update_rule(rule_id, updates, user_id=str(user_id))

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )

    await session.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    admin_payload: Annotated[dict, Depends(require_admin)],  # noqa: B008
    session: AsyncSession = Depends(get_session),  # noqa: B008
    redis_client: redis.Redis = Depends(get_redis_from_request),  # noqa: B008
) -> None:
    """Delete a correlation rule (admin-only).

    Args:
        rule_id: Rule ID
        session: Database session
        admin_payload: Admin JWT payload (required)
        redis_client: Async Redis client (injected from app state)
    """
    user_id = admin_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'sub' claim in token",
        )

    meta_emitter = get_meta_emitter(redis_client)

    service = RuleService(session, meta_emitter=meta_emitter)
    success = await service.delete_rule(rule_id, user_id=str(user_id))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )

    await session.commit()


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint.

    Returns:
        Health status
    """
    return {"status": "ok"}
