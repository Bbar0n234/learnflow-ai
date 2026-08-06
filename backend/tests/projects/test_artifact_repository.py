"""ArtifactRepository — integration against real Postgres (transactional rollback).

``created_at`` defaults to the transaction timestamp, so ordering tests set it
explicitly for a deterministic sequence (see the project-repo note).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.repositories.artifact import ArtifactRepository
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession

from tests.projects.conftest import ArtifactFactory, ThreadViewFactory

pytestmark = pytest.mark.integration

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def test_create_persists_and_get_by_id_reads_back(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    thread = await ThreadViewFactory.create(project=project)
    repo = ArtifactRepository(db_session)

    created = await repo.create(
        project_id=project.id,
        title="Summary",
        type="summary",
        content="# Hello",
        thread_id=thread.thread_id,
    )
    fetched = await repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.title == "Summary"
    assert fetched.content == "# Hello"
    assert fetched.thread_id == thread.thread_id


async def test_create_without_thread_leaves_thread_id_null(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    repo = ArtifactRepository(db_session)

    created = await repo.create(
        project_id=project.id, title="T", type="summary", content="c"
    )

    assert created.thread_id is None


async def test_get_by_id_missing_returns_none(db_session: AsyncSession) -> None:
    repo = ArtifactRepository(db_session)

    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_list_by_project_orders_by_created_at_desc(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    await ArtifactFactory.create(project=project, title="old", created_at=_BASE)
    await ArtifactFactory.create(
        project=project, title="new", created_at=_BASE + timedelta(hours=2)
    )
    await ArtifactFactory.create(
        project=project, title="mid", created_at=_BASE + timedelta(hours=1)
    )
    repo = ArtifactRepository(db_session)

    artifacts = await repo.list_by_project(project.id)

    assert [a.title for a in artifacts] == ["new", "mid", "old"]


async def test_list_by_project_applies_limit_and_offset(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    for i in range(5):
        await ArtifactFactory.create(
            project=project, title=f"a{i}", created_at=_BASE + timedelta(hours=i)
        )
    repo = ArtifactRepository(db_session)

    page = await repo.list_by_project(project.id, limit=2, offset=1)

    # Descending: a4, a3, a2, a1, a0 → offset 1, limit 2 → a3, a2.
    assert [a.title for a in page] == ["a3", "a2"]


async def test_list_by_project_excludes_other_projects(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    other = await ProjectFactory.create()
    await ArtifactFactory.create(project=project, title="mine")
    await ArtifactFactory.create(project=other, title="theirs")
    repo = ArtifactRepository(db_session)

    artifacts = await repo.list_by_project(project.id)

    assert [a.title for a in artifacts] == ["mine"]


async def test_count_by_project_counts_only_that_project(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    other = await ProjectFactory.create()
    await ArtifactFactory.create(project=project)
    await ArtifactFactory.create(project=project)
    await ArtifactFactory.create(project=other)
    repo = ArtifactRepository(db_session)

    assert await repo.count_by_project(project.id) == 2
    assert await repo.count_by_project(other.id) == 1


async def test_list_by_thread_orders_by_created_at_asc(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    thread = await ThreadViewFactory.create(project=project)
    other_thread = await ThreadViewFactory.create(project=project)
    await ArtifactFactory.create(
        project=project,
        thread_id=thread.thread_id,
        title="second",
        created_at=_BASE + timedelta(hours=1),
    )
    await ArtifactFactory.create(
        project=project,
        thread_id=thread.thread_id,
        title="first",
        created_at=_BASE,
    )
    await ArtifactFactory.create(
        project=project,
        thread_id=other_thread.thread_id,
        title="elsewhere",
    )
    repo = ArtifactRepository(db_session)

    artifacts = await repo.list_by_thread(thread.thread_id)

    assert [a.title for a in artifacts] == ["first", "second"]


async def test_set_message_id_updates_only_listed_artifacts(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    a1 = await ArtifactFactory.create(project=project)
    a2 = await ArtifactFactory.create(project=project)
    untouched = await ArtifactFactory.create(project=project)
    repo = ArtifactRepository(db_session)

    await repo.set_message_id([a1.id, a2.id], "msg-42")
    # Bulk UPDATE bypasses the identity map; detach so the reads below issue a
    # fresh async SELECT (expire_all would lazy-refresh outside the greenlet).
    db_session.expunge_all()

    assert (await repo.get_by_id(a1.id)).message_id == "msg-42"  # type: ignore[union-attr]
    assert (await repo.get_by_id(a2.id)).message_id == "msg-42"  # type: ignore[union-attr]
    assert (await repo.get_by_id(untouched.id)).message_id is None  # type: ignore[union-attr]


async def test_delete_removes_row(db_session: AsyncSession) -> None:
    artifact = await ArtifactFactory.create()
    repo = ArtifactRepository(db_session)

    await repo.delete(artifact)

    assert await repo.get_by_id(artifact.id) is None
