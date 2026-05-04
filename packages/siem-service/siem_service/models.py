"""SQLAlchemy ORM models for SIEM service."""

from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, Column, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy base model."""

    type_annotation_map = {dict[str, Any]: JSONB}


class SiemEvent(Base):
    """Security event storage model."""

    __tablename__ = "siem_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        comment="UUID for idempotency (at-least-once semantics)",
    )
    event_type = Column(
        String(255),
        nullable=False,
        comment="Event type string (e.g., 'auth.login.failed')",
    )
    severity = Column(
        String(20),
        nullable=False,
        comment="Severity: info | warning | critical",
    )
    event_timestamp = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="UTC timestamp from producer",
    )
    ingested_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
        comment="Consumer-side ingestion timestamp",
    )
    identifiers = Column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
        comment="Event identifiers: ip, user_id, request_id, etc.",
    )
    event_metadata = Column(
        JSONB,
        nullable=False,
        server_default="'{}'::jsonb",
        comment="Event-specific metadata dict (note: column name differs from Pydantic field 'metadata')",
    )
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default="now()",
    )

    __table_args__ = (
        Index("idx_siem_events_event_type", "event_type"),
        Index("idx_siem_events_severity", "severity"),
        Index("idx_siem_events_ingested_at", "ingested_at"),
        Index("idx_siem_events_event_timestamp", "event_timestamp"),
        Index("idx_siem_events_identifiers_gin", "identifiers", postgresql_using="gin"),
    )
