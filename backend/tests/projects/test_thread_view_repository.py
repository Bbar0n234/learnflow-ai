"""ThreadViewRepository — integration against real Postgres (transactional rollback).

Covers per-project queries, the user-scoped JOIN (``list_recent`` /
``count_by_user``), the security-blocked flag, and ``touch``. Ordering tests set
``updated_at`` explicitly (the column default is the transaction timestamp).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from app.models.artifact import Artifact
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.thread_view import ThreadViewRepository
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from tests.projects.conftest import ArtifactFactory, ThreadViewFactory

pytestmark = pytest.mark.integration

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def test_create_persists_and_get_by_id_reads_back(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    repo = ThreadViewRepository(db_session)

    created = await repo.create(project_id=project.id, title="My chat")
    fetched = await repo.get_by_id(created.thread_id)

    assert fetched is not None
    assert fetched.title == "My chat"
    assert fetched.project_id == project.id
    assert fetched.security_blocked is False


async def test_get_by_id_missing_returns_none(db_session: AsyncSession) -> None:
    repo = ThreadViewRepository(db_session)

    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_list_by_project_orders_by_updated_at_desc(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    await ThreadViewFactory.create(project=project, title="old", updated_at=_BASE)
    await ThreadViewFactory.create(
        project=project, title="new", updated_at=_BASE + timedelta(hours=2)
    )
    await ThreadViewFactory.create(
        project=project, title="mid", updated_at=_BASE + timedelta(hours=1)
    )
    repo = ThreadViewRepository(db_session)

    threads = await repo.list_by_project(project.id)

    assert [t.title for t in threads] == ["new", "mid", "old"]


async def test_list_by_project_applies_limit_and_offset(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    for i in range(4):
        await ThreadViewFactory.create(
            project=project, title=f"t{i}", updated_at=_BASE + timedelta(hours=i)
        )
    repo = ThreadViewRepository(db_session)

    page = await repo.list_by_project(project.id, limit=2, offset=1)

    # Descending: t3, t2, t1, t0 → offset 1, limit 2 → t2, t1.
    assert [t.title for t in page] == ["t2", "t1"]


async def test_count_by_project_counts_only_that_project(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    other = await ProjectFactory.create()
    await ThreadViewFactory.create(project=project)
    await ThreadViewFactory.create(project=project)
    await ThreadViewFactory.create(project=other)
    repo = ThreadViewRepository(db_session)

    assert await repo.count_by_project(project.id) == 2
    assert await repo.count_by_project(other.id) == 1


async def test_list_recent_returns_only_users_threads_with_project_loaded(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    owner_project = await ProjectFactory.create(user=owner)
    other_project = await ProjectFactory.create(user=other)
    await ThreadViewFactory.create(
        project=owner_project, title="mine", updated_at=_BASE + timedelta(hours=1)
    )
    await ThreadViewFactory.create(project=other_project, title="theirs")
    repo = ThreadViewRepository(db_session)

    # Detach the freshly-created rows so the identity map cannot satisfy the
    # ``.project`` access from cache: the relationship must come from the
    # ``contains_eager`` JOIN. Without this, even a regression that dropped the
    # eager-load (→ lazy-load → MissingGreenlet → 500 in prod) would stay green.
    db_session.expunge_all()

    threads = await repo.list_recent(owner.id)

    assert [t.title for t in threads] == ["mine"]
    # JOIN eager-loaded the parent project: accessing ``.project`` issues no
    # lazy SELECT (which under async would raise MissingGreenlet).
    assert "project" not in inspect(threads[0]).unloaded
    assert threads[0].project.user_id == owner.id


async def test_list_recent_orders_by_updated_at_desc(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    project = await ProjectFactory.create(user=owner)
    await ThreadViewFactory.create(project=project, title="old", updated_at=_BASE)
    await ThreadViewFactory.create(
        project=project, title="new", updated_at=_BASE + timedelta(hours=3)
    )
    repo = ThreadViewRepository(db_session)

    threads = await repo.list_recent(owner.id)

    assert [t.title for t in threads] == ["new", "old"]


async def test_count_by_user_counts_threads_across_users_projects(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    p1 = await ProjectFactory.create(user=owner)
    p2 = await ProjectFactory.create(user=owner)
    p_other = await ProjectFactory.create(user=other)
    await ThreadViewFactory.create(project=p1)
    await ThreadViewFactory.create(project=p2)
    await ThreadViewFactory.create(project=p_other)
    repo = ThreadViewRepository(db_session)

    assert await repo.count_by_user(owner.id) == 2
    assert await repo.count_by_user(other.id) == 1


async def test_update_changes_title_and_persists(db_session: AsyncSession) -> None:
    thread = await ThreadViewFactory.create(title="Before")
    repo = ThreadViewRepository(db_session)

    await repo.update(thread, title="After")
    refetched = await repo.get_by_id(thread.thread_id)

    assert refetched is not None
    assert refetched.title == "After"


async def test_touch_advances_updated_at(db_session: AsyncSession) -> None:
    thread = await ThreadViewFactory.create(updated_at=_BASE)
    repo = ThreadViewRepository(db_session)

    await repo.touch(thread)

    assert thread.updated_at > _BASE


async def test_mark_and_read_security_blocked_flag(
    db_session: AsyncSession,
) -> None:
    thread = await ThreadViewFactory.create()
    repo = ThreadViewRepository(db_session)

    assert await repo.is_security_blocked(thread.thread_id) is False

    await repo.mark_security_blocked(thread.thread_id)

    assert await repo.is_security_blocked(thread.thread_id) is True


async def test_is_security_blocked_missing_thread_returns_false(
    db_session: AsyncSession,
) -> None:
    repo = ThreadViewRepository(db_session)

    assert await repo.is_security_blocked(uuid.uuid4()) is False


async def test_delete_removes_row(db_session: AsyncSession) -> None:
    thread = await ThreadViewFactory.create()
    repo = ThreadViewRepository(db_session)

    await repo.delete(thread)

    assert await repo.get_by_id(thread.thread_id) is None


async def test_deleting_thread_nulls_artifact_thread_id(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    thread = await ThreadViewFactory.create(project=project)
    artifact = await ArtifactFactory.create(project=project, thread_id=thread.thread_id)

    # Delete the parent thread through Core (``sa.delete``), NOT the ORM
    # ``session.delete`` the repo uses: the ORM unit-of-work would itself NULL
    # the child FK in Python (no ``passive_deletes``), so an ORM delete would
    # pass even if the ``ON DELETE SET NULL`` DB constraint were dropped. The
    # Core statement bypasses the UoW and lets Postgres apply the constraint —
    # this is what exercises it.
    await db_session.execute(
        sa.delete(ThreadView).where(ThreadView.thread_id == thread.thread_id)
    )
    await db_session.flush()
    # Detach so the read issues a fresh async SELECT against Postgres rather
    # than returning the now-stale child from the identity map.
    db_session.expunge_all()

    surviving = await db_session.get(Artifact, artifact.id)
    assert surviving is not None
    assert surviving.thread_id is None
