"""Pydantic schemas for REST API responses."""

from datetime import datetime
from typing import Any
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
