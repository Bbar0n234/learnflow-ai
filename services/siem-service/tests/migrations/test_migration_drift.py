"""Drift guard for the siem-service alembic chain (independent of backend's)."""

from __future__ import annotations

from pathlib import Path

import pytest
from learnflow_testing.db import DbUrls, check_migration_drift

_ALEMBIC_INI = str(Path(__file__).resolve().parents[2] / "alembic.ini")


@pytest.mark.integration
def test_siem_migrations_match_models_no_drift(_migrated_db: DbUrls) -> None:
    check_migration_drift(
        _ALEMBIC_INI,
        _migrated_db.db_url,
        {"SIEM_DATABASE_URL": _migrated_db.db_url, "SIEM_JWT_SECRET": "test-secret"},
    )
