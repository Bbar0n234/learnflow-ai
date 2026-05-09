"""baseline correlation rules seed

Revision ID: 003
Revises: 002
Create Date: 2026-05-04

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    import json

    # Insert baseline correlation rules with ON CONFLICT DO NOTHING for idempotency
    rules = [
        {
            "name": "brute_force_auth",
            "description": "Множественные неудачные попытки входа с одного IP за 60 секунд",
            "rule_type": "threshold",
            "enabled": True,
            "severity": "critical",
            "config": {
                "event_type_pattern": "auth.login.failed",
                "threshold": 5,
                "window_seconds": 60,
                "group_key": "ip",
            },
        },
        {
            "name": "injection_spike",
            "description": "Всплеск попыток инъекций — превышен порог детекций по всем чекпойнтам",
            "rule_type": "aggregate",
            "enabled": True,
            "severity": "critical",
            "config": {
                "event_type_pattern": "agent.guard.%injection",
                "threshold": 10,
                "window_seconds": 300,
            },
        },
        {
            "name": "targeted_user_attack",
            "description": "Атака на конкретного пользователя — несколько срабатываний guard за 10 минут",
            "rule_type": "threshold",
            "enabled": True,
            "severity": "warning",
            "config": {
                "event_type_pattern": "agent.guard.%",
                "threshold": 3,
                "window_seconds": 600,
                "group_key": "user_id",
            },
        },
        {
            "name": "mass_suspicious",
            "description": "Массовые подозрительные вердикты по системе — превышен порог",
            "rule_type": "aggregate",
            "enabled": True,
            "severity": "critical",
            "config": {
                "event_type_pattern": "agent.guard.%suspicious",
                "threshold": 15,
                "window_seconds": 600,
            },
        },
    ]

    # Build raw SQL with properly escaped values
    values_list = []
    for rule in rules:
        name = str(rule["name"]).replace("'", "''")
        desc = str(rule["description"]).replace("'", "''")
        rule_type = str(rule["rule_type"])
        enabled = str(rule["enabled"]).lower()
        severity = str(rule["severity"])
        config_json = json.dumps(rule["config"]).replace("'", "''")
        values_list.append(
            f"('{name}', '{desc}', '{rule_type}', {enabled}, '{severity}', '{config_json}'::jsonb)"
        )

    sql = f"""
        INSERT INTO correlation_rules (name, description, rule_type, enabled, severity, config)
        VALUES {", ".join(values_list)}
        ON CONFLICT (name) DO NOTHING
    """

    op.execute(sa.text(sql))


def downgrade() -> None:
    """Downgrade schema."""
    # Delete baseline rules
    op.execute(
        sa.delete(sa.table("correlation_rules")).where(
            sa.text(
                "name IN ('brute_force_auth', 'injection_spike', 'targeted_user_attack', 'mass_suspicious')"
            )
        ),
    )
