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

    Session scope = **one container per pytest session**. Serially that is a
    single container for the whole run; under ``pytest -n`` each xdist worker
    is its own session, so each worker spins up its own container — workers are
    fully isolated (separate server *and* separate per-worker database), with no
    ``CREATE DATABASE`` races between workers (different servers entirely).

    Within a session both services point their own per-worker database at this
    container; only the SQLAlchemy driver in the URL differs (backend
    ``psycopg`` / siem ``asyncpg``). The container is lazy — it starts only when
    a test requests it.
    """
    with PostgresContainer("postgres:16-alpine") as container:
        yield container
