"""Regression guard for finding F1 — the chat row must stay writable mid-stream.

``send_message`` touches (``UPDATE thread_views SET updated_at=now()``) the chat
row it is about to stream into, and ``get_db_session`` commits the request
session only after the SSE generator is exhausted. An uncommitted touch
therefore keeps a row lock for the whole stream, and the background auto-title
task — a *different* session — blocks on that very row: ``title_updated`` can
never land inside the stream, and on a run longer than the statement timeout the
title is lost outright. The fix is an explicit commit right after the touch;
this suite is the test that would have caught its absence.

**Why this level.** The race only exists between two real Postgres transactions,
so neither in-memory fakes (``test_auto_title_relay.py``,
``test_chat_title_generator.py``) nor the ASGI route can express it: the shared
``db_session`` harness binds the handler's session to an outer transaction with
``join_transaction_mode="create_savepoint"``, so a production ``commit()``
releases a savepoint and never a row lock — the very thing under test would be
invisible. This suite therefore drives ``ChatService.send_message`` directly over
a genuine session on the test engine, with genuinely committed fixture data,
which is the narrow "commit and clean up instead of the shared transaction"
route the harness sanctions for tests that need two concurrent connections
(``tests/conftest.py`` LIMITATION, ``conventions/testing.md`` § HTTP-тесты).

The second session does exactly what ``ChatTitleGenerator._run`` does — a
``ThreadViewRepository.update`` + ``commit`` of its own — under a ``lock_timeout``
so a blocked write fails fast and loudly instead of hanging the suite. The
timeout bounds *waiting for a lock*, never the statement itself: on an unlocked
row it is never reached, so it is an upper bound on failure and not a condition
of success.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.artifact import ArtifactRepository
from app.repositories.thread_view import ThreadViewRepository
from app.services.chat import ChatService
from app.services.constants import DEFAULT_CHAT_TITLE
from psycopg.errors import LockNotAvailable
from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.chat.conftest import FakeAgentRunner, text_chunk_event

pytestmark = pytest.mark.integration

_USER_TEXT = "Объясни, что такое дискриминант"
_GENERATED_TITLE = "Квадратные уравнения"


@dataclass(frozen=True)
class CommittedChat:
    """Ids of a chat that exists in the database for real (outside any test tx)."""

    user_id: uuid.UUID
    project_id: uuid.UUID
    thread_id: uuid.UUID


@pytest_asyncio.fixture
async def committed_chat(engine: AsyncEngine) -> AsyncIterator[CommittedChat]:
    """A user + project + placeholder-titled chat, committed and cleaned up.

    The shared transactional ``db_session`` cannot back this test: rows living in
    an uncommitted transaction are invisible to the second connection, and its
    savepoint-joined commits never release row locks. So the fixture writes real
    rows and deletes them in teardown; ``ON DELETE CASCADE`` from ``users``
    carries the project and the chat away with the user.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(
            name=f"row-lock-{uuid.uuid4()}",
            password_hash="argon2-placeholder-hash",
        )
        project = Project(name="row-lock", user=user)
        thread = ThreadView(project=project, title=DEFAULT_CHAT_TITLE)
        session.add(thread)
        await session.commit()
        chat = CommittedChat(
            user_id=user.id,
            project_id=project.id,
            thread_id=thread.thread_id,
        )
    try:
        yield chat
    finally:
        async with session_factory() as session:
            await session.execute(delete(User).where(User.id == chat.user_id))
            await session.commit()


async def _write_title_from_its_own_session(
    session_factory: async_sessionmaker[AsyncSession], thread_id: uuid.UUID
) -> None:
    """Write a title the way the background task does — own session, own commit.

    ``lock_timeout`` turns "the row is still locked by the request" from an
    indefinite hang into an immediate, named failure.
    """
    async with session_factory() as session:
        await session.execute(text("SET LOCAL lock_timeout = '1s'"))
        repo = ThreadViewRepository(session)
        thread_view = await repo.get_by_id(thread_id)
        assert thread_view is not None
        try:
            await repo.update(thread_view, title=_GENERATED_TITLE)
            await session.commit()
        except OperationalError as exc:
            if not isinstance(exc.orig, LockNotAvailable):
                raise
            pytest.fail(
                "the background title write waited on the chat row while the "
                "stream was open: send_message left its touch UPDATE "
                "uncommitted in the request session (finding F1)"
            )


async def _stored_title(
    session_factory: async_sessionmaker[AsyncSession], thread_id: uuid.UUID
) -> str | None:
    """Column-level read on a fresh session — no identity map, no stale snapshot."""
    async with session_factory() as session:
        return await session.scalar(
            select(ThreadView.title).where(ThreadView.thread_id == thread_id)
        )


async def test_send_message_leaves_the_chat_row_writable_while_streaming(
    engine: AsyncEngine,
    committed_chat: CommittedChat,
    fake_runner: FakeAgentRunner,
) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    fake_runner.events = [text_chunk_event("Дискриминант"), text_chunk_event(" — это")]
    fake_runner.last_ai_message_id = "m1"

    async with session_factory() as request_session:
        service = ChatService(
            thread_view_repo=ThreadViewRepository(request_session),
            agent_runner=fake_runner,
            artifact_repo=ArtifactRepository(request_session),
            session=request_session,
        )
        stream = service.send_message(
            thread_id=committed_chat.thread_id,
            project_id=committed_chat.project_id,
            user_id=committed_chat.user_id,
            content=_USER_TEXT,
        )

        # One event in: the touch is behind us and the stream is still open —
        # exactly the window in which the title task tries to write.
        first = await anext(stream)
        assert first.type == "text_chunk"

        await _write_title_from_its_own_session(
            session_factory, committed_chat.thread_id
        )

        remaining = [event.type async for event in stream]

    # The concurrent write neither blocked nor cost the stream anything: it runs
    # to completion and the title is durably there for the client to see.
    assert remaining == ["text_chunk", "done"]
    assert await _stored_title(session_factory, committed_chat.thread_id) == (
        _GENERATED_TITLE
    )
