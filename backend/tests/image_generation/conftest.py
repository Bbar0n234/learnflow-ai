"""Local fixtures for the feat-010 image-generation scope (T1).

The ``generate_image`` tool opens its *own* transaction through an injected
``session_factory`` (``async with session_factory() as session,
session.begin()``) — unlike a handler, it does not receive the test's
``db_session``. To integration-test it against real Postgres while keeping the
transactional-rollback isolation of the harness, this conftest provides a
``tool_session_factory`` whose every session is bound to one outer connection +
transaction (rolled back in teardown). The tool's ``session.begin()`` becomes a
savepoint that commits into that outer transaction, so the writes are visible to
the ``seed_session`` reader on the same connection and discarded after the test.

``seed_session`` binds the shared ``learnflow_testing`` factories (User/Project)
and the scope-local ``ThreadViewFactory`` to that same connection, so seeded
FK parents are visible to the tool's sibling sessions.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from app.models.thread_view import ThreadView
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory
from factory.declarations import Sequence, SubFactory
from learnflow_testing.factories import ProjectFactory, bind_session
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession


class ThreadViewFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = ThreadView
        sqlalchemy_session_persistence = "flush"

    title = Sequence(lambda n: f"thread-{n}")
    project = SubFactory(ProjectFactory)


@pytest_asyncio.fixture
async def outer_conn(engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """One connection with an outer transaction rolled back in teardown.

    All sessions in a test (seed reader + the tool's own sessions) bind here, so
    everything lives in a single transaction that is discarded after the test.
    """
    conn = await engine.connect()
    trans = await conn.begin()
    try:
        yield conn
    finally:
        await trans.rollback()
        await conn.close()


def _bound_session(conn: AsyncConnection) -> AsyncSession:
    return AsyncSession(
        bind=conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )


@pytest.fixture
def tool_session_factory(
    outer_conn: AsyncConnection,
) -> Callable[[], AsyncSession]:
    """A ``session_factory`` for the tool: fresh sibling session on ``outer_conn``."""

    def _make() -> AsyncSession:
        return _bound_session(outer_conn)

    return _make


@pytest_asyncio.fixture
async def seed_session(outer_conn: AsyncConnection) -> AsyncIterator[AsyncSession]:
    """A reader/seeder session on ``outer_conn`` with factories bound to it."""
    session = _bound_session(outer_conn)
    bind_session(session)
    bind_session(session, ThreadViewFactory)
    try:
        yield session
    finally:
        await session.close()
