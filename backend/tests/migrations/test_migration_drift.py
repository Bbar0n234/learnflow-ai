"""Drift guard for the backend alembic chain.

Asserts the models and migrations agree: ``alembic check`` against a freshly
migrated test DB must find nothing to autogenerate. The siem-service chain has
its own guard in that package — the two chains are never mixed in one run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from learnflow_testing.db import DbUrls, check_migration_drift

_ALEMBIC_INI = str(Path(__file__).resolve().parents[2] / "alembic.ini")


@pytest.mark.integration
def test_backend_migrations_match_models_no_drift(_migrated_db: DbUrls) -> None:
    check_migration_drift(
        _ALEMBIC_INI,
        _migrated_db.db_url,
        {"DATABASE_URL": _migrated_db.db_url, "JWT_SECRET": "test-secret"},
    )
