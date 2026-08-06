"""Pydantic schemas for REST API responses."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SecurityEventIdentifiersResponse(BaseModel):
    """Security event identifiers in API response."""

    ip: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    thread_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    user_agent_hash: str | None = None


class EventResponse(BaseModel):
    """Security event API response."""

    event_id: UUID = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Event type")
    severity: str = Field(..., description="Severity level")
    event_timestamp: datetime = Field(..., description="Event creation time")
    ingested_at: datetime = Field(..., description="Ingestion time")
    identifiers: SecurityEventIdentifiersResponse = Field(
        ..., description="Identifiers"
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata")

    class Config:
        """Pydantic config."""

        from_attributes = True


class PaginatedEventsResponse(BaseModel):
    """Paginated events response."""

    items: list[EventResponse] = Field(..., description="List of events")
    total: int = Field(..., description="Total number of events")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Offset")


class EventFilterParams(BaseModel):
    """Query parameters for event filtering."""

    event_type: str | None = Field(None, description="Filter by event type")
    severity: str | None = Field(None, description="Filter by severity")
    from_timestamp: datetime | None = Field(
        None, alias="from", description="Start timestamp"
    )
    to_timestamp: datetime | None = Field(None, alias="to", description="End timestamp")
    limit: int = Field(50, ge=1, le=200, description="Items per page")
    offset: int = Field(0, ge=0, description="Page offset")

    class Config:
        """Pydantic config."""

        populate_by_name = True


class AlertResponse(BaseModel):
    """Alert API response."""

    id: int = Field(..., description="Alert ID")
    rule_id: int = Field(..., description="Correlation rule ID")
    severity: str = Field(..., description="Severity level")
    status: str = Field(
        ..., description="Alert status (new, acknowledged, resolved, expired)"
    )
    group_key: str | None = Field(None, description="Grouping key if applicable")
    matched_events_count: int = Field(..., description="Number of matched events")
    first_event_id: UUID = Field(..., description="First matched event ID")
    latest_event_id: UUID = Field(..., description="Latest matched event ID")
    created_at: datetime = Field(..., description="Alert creation time")
    updated_at: datetime = Field(..., description="Alert update time")
    acknowledged_at: datetime | None = Field(None, description="Acknowledgement time")
    acknowledged_by: str | None = Field(None, description="User who acknowledged")
    resolved_at: datetime | None = Field(None, description="Resolution time")
    resolved_by: str | None = Field(None, description="User who resolved")

    class Config:
        """Pydantic config."""

        from_attributes = True


class AlertPatchRequest(BaseModel):
    """Request body for patching an alert."""

    status: Literal["acknowledged", "resolved"] = Field(
        ..., description="New status (acknowledged or resolved)"
    )


class PaginatedAlertsResponse(BaseModel):
    """Paginated alerts response."""

    items: list[AlertResponse] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total number of alerts")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Offset")


class RuleConfigResponse(BaseModel):
    """Correlation rule configuration."""

    event_type_pattern: str | None = None
    event_a_pattern: str | None = None
    event_b_pattern: str | None = None
    threshold: int | None = None
    window_seconds: int | None = None
    group_key: str | None = None

    class Config:
        """Pydantic config."""

        from_attributes = True


class RuleResponse(BaseModel):
    """Correlation rule API response."""

    id: int = Field(..., description="Rule ID")
    name: str = Field(..., description="Rule name")
    description: str | None = Field(None, description="Rule description")
    rule_type: str = Field(
        ..., description="Rule type (threshold, sequence, aggregate)"
    )
    enabled: bool = Field(..., description="Whether rule is enabled")
    severity: str = Field(..., description="Alert severity for this rule")
    config: dict[str, Any] = Field(..., description="Rule configuration")
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Update time")

    class Config:
        """Pydantic config."""

        from_attributes = True


class RuleCreateRequest(BaseModel):
    """Request body for creating a rule."""

    name: str = Field(..., description="Rule name")
    description: str | None = Field(None, description="Rule description")
    rule_type: Literal["threshold", "sequence", "aggregate"] = Field(
        ..., description="Rule type"
    )
    enabled: bool = Field(True, description="Enable rule")
    severity: Literal["info", "warning", "critical"] = Field(
        "warning", description="Alert severity"
    )
    config: dict[str, Any] = Field(..., description="Rule configuration")


class RuleUpdateRequest(BaseModel):
    """Request body for updating a rule."""

    name: str | None = None
    description: str | None = None
    rule_type: Literal["threshold", "sequence", "aggregate"] | None = None
    enabled: bool | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    config: dict[str, Any] | None = None


class PaginatedRulesResponse(BaseModel):
    """Paginated rules response."""

    items: list[RuleResponse] = Field(..., description="List of rules")
    total: int = Field(..., description="Total number of rules")
    limit: int = Field(..., description="Items per page")
    offset: int = Field(..., description="Offset")
