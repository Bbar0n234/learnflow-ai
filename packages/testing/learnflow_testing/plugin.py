"""Cross-project pytest plugin (loaded via the ``pytest11`` entry point).

Each package runs pytest with its own ``--rootdir`` (see the Makefile), which
scopes ``conftest.py`` discovery to that package — a repo-root ``conftest.py``
would not load. The entry-point plugin is the mechanism that shares genuinely
cross-cutting fixtures across packages. Package-specific wiring (engine,
migrations, auth client) lives in each package's ``tests/conftest.py``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[object]:
    """Session-scoped Postgres via testcontainers (cheap, immutable).

    Both services point their own per-worker database at this one container;
    only the SQLAlchemy driver in the URL differs (backend ``psycopg`` / siem
    ``asyncpg``). The container is lazy — it starts only when a test requests it.
    """
    with PostgresContainer("postgres:16-alpine") as container:
        yield container
