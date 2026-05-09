"""Alert models for SIEM."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AlertStatus(BaseModel):
    """Alert status type."""

    status: Literal["new", "acknowledged", "resolved"] = Field(
        ..., description="Current alert status"
    )


class AlertDTO(BaseModel):
    """Alert data transfer object for REST API."""

    id: UUID = Field(..., description="Alert ID")
    rule_id: UUID = Field(..., description="Correlation rule ID")
    severity: Literal["info", "warning", "critical"] = Field(
        ..., description="Alert severity"
    )
    status: Literal["new", "acknowledged", "resolved"] = Field(
        default="new", description="Current status"
    )
    matched_events_count: int = Field(default=0, description="Number of matched events")
    group_key: str | None = Field(None, description="Group key value if grouped")
    created_at: datetime = Field(..., description="Alert creation time")
    acknowledged_at: datetime | None = Field(None, description="When acknowledged")
    resolved_at: datetime | None = Field(None, description="When resolved")
