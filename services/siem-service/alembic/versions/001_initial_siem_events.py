"""initial siem events schema

Revision ID: 001
Revises:
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create siem_events table
    op.create_table(
        "siem_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "event_id",
            sa.UUID(),
            nullable=False,
            comment="UUID for idempotency (at-least-once semantics)",
        ),
        sa.Column(
            "event_type",
            sa.String(length=255),
            nullable=False,
            comment="Event type string (e.g., 'auth.login.failed')",
        ),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            comment="Severity: info | warning | critical",
        ),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="UTC timestamp from producer",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Consumer-side ingestion timestamp",
        ),
        sa.Column(
            "identifiers",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Event identifiers: ip, user_id, request_id, etc.",
        ),
        sa.Column(
            "event_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Event-specific metadata dict",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )

    # Create indexes
    op.create_index(
        "idx_siem_events_event_type",
        "siem_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "idx_siem_events_severity",
        "siem_events",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "idx_siem_events_ingested_at",
        "siem_events",
        ["ingested_at"],
        unique=False,
    )
    op.create_index(
        "idx_siem_events_event_timestamp",
        "siem_events",
        ["event_timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_siem_events_identifiers_gin",
        "siem_events",
        ["identifiers"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_siem_events_identifiers_gin", table_name="siem_events")
    op.drop_index("idx_siem_events_event_timestamp", table_name="siem_events")
    op.drop_index("idx_siem_events_ingested_at", table_name="siem_events")
    op.drop_index("idx_siem_events_severity", table_name="siem_events")
    op.drop_index("idx_siem_events_event_type", table_name="siem_events")
    op.drop_table("siem_events")
