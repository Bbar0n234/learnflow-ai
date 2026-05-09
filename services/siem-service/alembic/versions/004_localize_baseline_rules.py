"""localize baseline correlation rules descriptions

Revision ID: 004
Revises: 003
Create Date: 2026-05-05

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, Sequence[str], None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRANSLATIONS = [
    (
        "brute_force_auth",
        "Multiple failed login attempts from same IP within 60 seconds",
        "Множественные неудачные попытки входа с одного IP за 60 секунд",
    ),
    (
        "injection_spike",
        "High volume of injection attempts detected across any checkpoint",
        "Всплеск попыток инъекций — превышен порог детекций по всем чекпойнтам",
    ),
    (
        "targeted_user_attack",
        "Multiple guard detections on single user within 10 minutes",
        "Атака на конкретного пользователя — несколько срабатываний guard за 10 минут",
    ),
    (
        "mass_suspicious",
        "High volume of suspicious verdicts detected system-wide",
        "Массовые подозрительные вердикты по системе — превышен порог",
    ),
]


def _sql_quote(value: str) -> str:
    """Quote static migration strings for online and offline Alembic modes."""
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    """Replace English descriptions with Russian for baseline rules."""
    for name, en, ru in _TRANSLATIONS:
        op.execute(
            "UPDATE correlation_rules "
            f"SET description = {_sql_quote(ru)} "
            f"WHERE name = {_sql_quote(name)} AND description = {_sql_quote(en)}"
        )


def downgrade() -> None:
    """Revert Russian descriptions back to English."""
    for name, en, ru in _TRANSLATIONS:
        op.execute(
            "UPDATE correlation_rules "
            f"SET description = {_sql_quote(en)} "
            f"WHERE name = {_sql_quote(name)} AND description = {_sql_quote(ru)}"
        )
