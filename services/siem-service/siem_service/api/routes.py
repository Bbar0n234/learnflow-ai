"""REST API routes for SIEM service."""

from datetime import datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from siem_service.api.deps import AdminPayload, MetaEmitterDep, SessionDep
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
from siem_service.services import AlertService, EventService, RuleService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/security", tags=["security"])

LimitQuery = Annotated[int, Query(ge=1, le=200, description="Items per page")]
OffsetQuery = Annotated[int, Query(ge=0, description="Page offset")]


def _require_user_id(admin_payload: dict) -> str:
    user_id = admin_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'sub' claim in token",
        )
    return str(user_id)


@router.get("/events", response_model=PaginatedEventsResponse)
async def list_events(
    session: SessionDep,
    event_type: Annotated[str | None, Query(description="Filter by event type")] = None,
    severity: Annotated[str | None, Query(description="Filter by severity")] = None,
    from_timestamp: Annotated[
        datetime | None, Query(alias="from", description="Start time")
    ] = None,
    to_timestamp: Annotated[
        datetime | None, Query(alias="to", description="End time")
    ] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> PaginatedEventsResponse:
    """List security events with filtering and pagination."""
    filters = EventFilterParams(
        event_type=event_type,
        severity=severity,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
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
    admin_payload: AdminPayload,
    session: SessionDep,
    severity: Annotated[str | None, Query(description="Filter by severity")] = None,
    status_filter: Annotated[
        str | None, Query(alias="status", description="Filter by status")
    ] = None,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> PaginatedAlertsResponse:
    """List security alerts with filtering and pagination (admin-only)."""
    service = AlertService(session)
    alerts, total = await service.list_alerts(
        severity=severity,
        status=status_filter,
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
    admin_payload: AdminPayload,
    session: SessionDep,
) -> AlertResponse:
    """Get alert details (admin-only)."""
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
    admin_payload: AdminPayload,
    session: SessionDep,
    meta_emitter: MetaEmitterDep,
) -> AlertResponse:
    """Update alert status (admin-only)."""
    if request.status not in ("acknowledged", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'acknowledged' or 'resolved'",
        )

    user_id = _require_user_id(admin_payload)

    service = AlertService(session, meta_emitter=meta_emitter)

    if request.status == "acknowledged":
        alert = await service.acknowledge_alert(alert_id, user_id)
    else:
        alert = await service.resolve_alert(alert_id, user_id)

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
    admin_payload: AdminPayload,
    session: SessionDep,
    limit: LimitQuery = 50,
    offset: OffsetQuery = 0,
) -> PaginatedRulesResponse:
    """List correlation rules (admin-only)."""
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
    admin_payload: AdminPayload,
    session: SessionDep,
) -> RuleResponse:
    """Get rule details (admin-only)."""
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
    admin_payload: AdminPayload,
    session: SessionDep,
    meta_emitter: MetaEmitterDep,
) -> RuleResponse:
    """Create a new correlation rule (admin-only)."""
    user_id = _require_user_id(admin_payload)

    service = RuleService(session, meta_emitter=meta_emitter)
    rule = await service.create_rule(
        name=request.name,
        rule_type=request.rule_type,
        config=request.config,
        severity=request.severity,
        description=request.description,
        enabled=request.enabled,
        user_id=user_id,
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
    admin_payload: AdminPayload,
    session: SessionDep,
    meta_emitter: MetaEmitterDep,
) -> RuleResponse:
    """Update a correlation rule (admin-only)."""
    user_id = _require_user_id(admin_payload)

    service = RuleService(session, meta_emitter=meta_emitter)

    # Filter out None values
    updates = {k: v for k, v in request.model_dump().items() if v is not None}

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    rule = await service.update_rule(rule_id, updates, user_id=user_id)

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )

    await session.commit()
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: int,
    admin_payload: AdminPayload,
    session: SessionDep,
    meta_emitter: MetaEmitterDep,
) -> None:
    """Delete a correlation rule (admin-only)."""
    user_id = _require_user_id(admin_payload)

    service = RuleService(session, meta_emitter=meta_emitter)
    success = await service.delete_rule(rule_id, user_id=user_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )

    await session.commit()
