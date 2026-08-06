"""Cross-project pytest plugin (loaded via the ``pytest11`` entry point).

Each package runs pytest with its own ``--rootdir`` (see the Makefile), which
scopes ``conftest.py`` discovery to that package — a repo-root ``conftest.py``
would not load. The entry-point plugin is the mechanism that shares genuinely
cross-cutting fixtures across packages. Package-specific wiring (engine,
migrations, auth client) lives in each package's ``tests/conftest.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


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


@pytest.fixture(scope="session")
def redis_container() -> Iterator[object]:
    """Session-scoped Redis via testcontainers (cheap, immutable).

    Mirrors :func:`postgres_container`: one container per pytest session. Serially
    that is a single container for the whole run; under ``pytest -n`` each xdist
    worker is its own session, so each worker spins up its own container — fully
    isolated, no cross-worker key collisions. The container is lazy — it starts
    only when a test requests it. Image pinned to match docker-compose.
    """
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container: object) -> str:
    """Connection URL (``redis://host:port/0``) for the session Redis container.

    Both backend (``redis_url``) and siem (``SIEM_REDIS_URL``) point at this one
    container; per-test isolation comes from the function-scoped ``redis_client``
    fixture flushing the database around each test.
    """
    host = redis_container.get_container_host_ip()  # type: ignore[attr-defined]
    port = redis_container.get_exposed_port(6379)  # type: ignore[attr-defined]
    return f"redis://{host}:{port}/0"


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[aioredis.Redis]:
    """Function-scoped async Redis client with per-test isolation via ``flushdb``.

    Flushes before *and* after the test so state never leaks between tests sharing
    the session container — the Redis analogue of the Postgres transactional
    rollback (``transactional_session``). Hand the same client (or its URL) to the
    code under test, e.g. ``TraceStore(redis_client)``.
    """
    client: aioredis.Redis = aioredis.Redis.from_url(redis_url)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()
