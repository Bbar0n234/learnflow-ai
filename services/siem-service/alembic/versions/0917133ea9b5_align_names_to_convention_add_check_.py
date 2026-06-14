# Manual migration: переименование constraints/индексов под naming convention
# (RENAME не покрывается autogenerate) + CHECK constraints (autogenerate их не детектит).
"""align names to convention, add check constraints

Revision ID: 0917133ea9b5
Revises: 004
Create Date: 2026-06-12 21:51:21.101209

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0917133ea9b5"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, old_name, new_name).
# Renames условные: на свежей БД naming convention из target_metadata действует уже
# в ранних миграциях, поэтому безымянные constraints (PK/UNIQUE) сразу получают
# целевые имена и rename пропускается; явно названные (FK, индексы) существуют под
# старыми именами на любой БД. Rename PK/UNIQUE переименовывает и их индексы.
_CONSTRAINT_RENAMES = [
    # primary keys
    ("correlation_rules", "correlation_rules_pkey", "pk_correlation_rules"),
    ("siem_alerts", "siem_alerts_pkey", "pk_siem_alerts"),
    ("siem_events", "siem_events_pkey", "pk_siem_events"),
    # foreign keys
    ("siem_alerts", "fk_siem_alerts_rule_id", "fk_siem_alerts_rule_id_correlation_rules"),
    (
        "siem_alerts",
        "fk_siem_alerts_first_event_id",
        "fk_siem_alerts_first_event_id_siem_events",
    ),
    (
        "siem_alerts",
        "fk_siem_alerts_latest_event_id",
        "fk_siem_alerts_latest_event_id_siem_events",
    ),
    # unique constraints
    ("correlation_rules", "correlation_rules_name_key", "uq_correlation_rules_name"),
    ("siem_events", "siem_events_event_id_key", "uq_siem_events_event_id"),
]

# (old_name, new_name)
_INDEX_RENAMES = [
    ("idx_correlation_rules_enabled", "ix_correlation_rules_enabled"),
    ("idx_siem_alerts_created_at", "ix_siem_alerts_created_at"),
    ("idx_siem_alerts_rule_id", "ix_siem_alerts_rule_id"),
    ("idx_siem_alerts_status", "ix_siem_alerts_status"),
    ("idx_siem_events_event_timestamp", "ix_siem_events_event_timestamp"),
    ("idx_siem_events_event_type", "ix_siem_events_event_type"),
    ("idx_siem_events_identifiers_gin", "ix_siem_events_identifiers_gin"),
    ("idx_siem_events_ingested_at", "ix_siem_events_ingested_at"),
]

# (table, name, expression) — наборы значений зашиты в код (стратегии,
# жизненный цикл алерта), расширение набора = миграция рядом с кодом.
_CHECKS = [
    ("siem_events", "ck_siem_events_severity", "severity IN ('info', 'warning', 'critical')"),
    (
        "correlation_rules",
        "ck_correlation_rules_rule_type",
        "rule_type IN ('threshold', 'sequence', 'aggregate')",
    ),
    (
        "correlation_rules",
        "ck_correlation_rules_severity",
        "severity IN ('info', 'warning', 'critical')",
    ),
    ("siem_alerts", "ck_siem_alerts_severity", "severity IN ('info', 'warning', 'critical')"),
    (
        "siem_alerts",
        "ck_siem_alerts_status",
        "status IN ('new', 'acknowledged', 'resolved', 'expired')",
    ),
]


def _constraint_exists(table: str, name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint"
                " WHERE conname = :name AND conrelid = CAST(:table AS regclass)"
            ),
            {"name": name, "table": table},
        )
        .scalar()
    )


def _index_exists(name: str) -> bool:
    return bool(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
            ),
            {"name": name},
        )
        .scalar()
    )


def upgrade() -> None:
    """Upgrade schema."""
    for table, old, new in _CONSTRAINT_RENAMES:
        if _constraint_exists(table, old):
            op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{old}" TO "{new}"')
    for old, new in _INDEX_RENAMES:
        if _index_exists(old):
            op.execute(f'ALTER INDEX "{old}" RENAME TO "{new}"')
    for table, name, expr in _CHECKS:
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" CHECK ({expr})')


def downgrade() -> None:
    """Downgrade schema."""
    for table, name, _expr in reversed(_CHECKS):
        op.execute(f'ALTER TABLE {table} DROP CONSTRAINT "{name}"')
    for old, new in reversed(_INDEX_RENAMES):
        if _index_exists(new):
            op.execute(f'ALTER INDEX "{new}" RENAME TO "{old}"')
    for table, old, new in reversed(_CONSTRAINT_RENAMES):
        if _constraint_exists(table, new):
            op.execute(f'ALTER TABLE {table} RENAME CONSTRAINT "{new}" TO "{old}"')
