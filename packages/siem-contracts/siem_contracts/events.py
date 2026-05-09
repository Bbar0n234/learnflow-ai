"""Security event contract models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from siem_contracts.vocabulary import EventType


class SecurityEventIdentifiers(BaseModel):
    """Identifiers for correlating security events."""

    ip: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    thread_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    user_agent_hash: str | None = None


class SecurityEvent(BaseModel):
    """Canonical security event contract between producer and consumer."""

    event_id: UUID = Field(..., description="Unique event ID for idempotency")
    event_type: EventType = Field(..., description="Hierarchical event type")
    severity: Literal["info", "warning", "critical"] = Field(
        ..., description="Event severity level"
    )
    timestamp: datetime = Field(..., description="UTC timestamp of event creation")
    identifiers: SecurityEventIdentifiers = Field(
        default_factory=SecurityEventIdentifiers,
        description="Identifiers for correlation",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific metadata"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": "auth.login.failed",
                "severity": "warning",
                "timestamp": "2024-01-01T12:00:00Z",
                "identifiers": {
                    "ip": "192.168.1.1",
                    "request_id": "req-123",
                },
                "metadata": {
                    "domain": "auth",
                    "reason": "invalid_credentials",
                },
            }
        }
