"""alerts and rules tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create correlation_rules table
    op.create_table(
        "correlation_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
            comment="Rule name (unique)",
        ),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="Rule description",
        ),
        sa.Column(
            "rule_type",
            sa.String(length=50),
            nullable=False,
            comment="Rule type: threshold | sequence | aggregate",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment="Rule enabled status",
        ),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'warning'"),
            comment="Alert severity for this rule",
        ),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Rule configuration (per rule_type)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Index for enabled status (for efficient rule loading)
    op.create_index(
        "idx_correlation_rules_enabled",
        "correlation_rules",
        ["enabled"],
        unique=False,
    )

    # Create siem_alerts table
    op.create_table(
        "siem_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rule_id",
            sa.BigInteger(),
            nullable=False,
            comment="FK to correlation_rules",
        ),
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            comment="Alert severity (info | warning | critical)",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'new'"),
            comment="Alert status: new | acknowledged | resolved",
        ),
        sa.Column(
            "group_key",
            sa.String(length=255),
            nullable=True,
            comment="Grouping key (ip, user_id, etc.) or NULL for no grouping",
        ),
        sa.Column(
            "matched_events_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Number of events matched for this alert",
        ),
        sa.Column(
            "first_event_id",
            sa.UUID(),
            nullable=False,
            comment="FK to siem_events (first matched event)",
        ),
        sa.Column(
            "latest_event_id",
            sa.UUID(),
            nullable=False,
            comment="FK to siem_events (latest matched event)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when alert was acknowledged",
        ),
        sa.Column(
            "acknowledged_by",
            sa.String(length=255),
            nullable=True,
            comment="User ID who acknowledged the alert",
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when alert was resolved",
        ),
        sa.Column(
            "resolved_by",
            sa.String(length=255),
            nullable=True,
            comment="User ID who resolved the alert",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["correlation_rules.id"],
            ondelete="RESTRICT",
            name="fk_siem_alerts_rule_id",
        ),
        sa.ForeignKeyConstraint(
            ["first_event_id"],
            ["siem_events.event_id"],
            ondelete="RESTRICT",
            name="fk_siem_alerts_first_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["latest_event_id"],
            ["siem_events.event_id"],
            ondelete="RESTRICT",
            name="fk_siem_alerts_latest_event_id",
        ),
    )

    # Indexes for efficient querying
    op.create_index(
        "idx_siem_alerts_rule_id",
        "siem_alerts",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        "idx_siem_alerts_status",
        "siem_alerts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "idx_siem_alerts_created_at",
        "siem_alerts",
        ["created_at"],
        unique=False,
    )

    # Composite index for open-alert lookup:
    # Find open alerts for (rule_id, group_key) created within 24h
    op.create_index(
        "idx_siem_alerts_open_alert_lookup",
        "siem_alerts",
        ["rule_id", "group_key", "status"],
        unique=False,
        postgresql_where=sa.text("status = 'new'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_siem_alerts_open_alert_lookup",
        table_name="siem_alerts",
    )
    op.drop_index(
        "idx_siem_alerts_created_at",
        table_name="siem_alerts",
    )
    op.drop_index(
        "idx_siem_alerts_status",
        table_name="siem_alerts",
    )
    op.drop_index(
        "idx_siem_alerts_rule_id",
        table_name="siem_alerts",
    )
    op.drop_table("siem_alerts")

    op.drop_index(
        "idx_correlation_rules_enabled",
        table_name="correlation_rules",
    )
    op.drop_table("correlation_rules")
