"""ProjectRepository — integration against real Postgres (transactional rollback).

Note on timestamps: ``func.now()`` (the column server-default) returns the
*transaction* start time, so every row created in one test shares it. Ordering
tests therefore set ``updated_at`` explicitly to get a deterministic sequence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.user import User
from app.repositories.project import ProjectRepository
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def test_create_persists_and_get_by_id_reads_back(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = ProjectRepository(db_session)

    created = await repo.create(user_id=user.id, name="Created")
    fetched = await repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Created"
    assert fetched.user_id == user.id


async def test_get_by_id_missing_returns_none(db_session: AsyncSession) -> None:
    repo = ProjectRepository(db_session)

    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_list_by_user_orders_by_updated_at_desc(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    await ProjectFactory.create(user=user, name="oldest", updated_at=_BASE)
    await ProjectFactory.create(
        user=user, name="newest", updated_at=_BASE + timedelta(hours=2)
    )
    await ProjectFactory.create(
        user=user, name="middle", updated_at=_BASE + timedelta(hours=1)
    )
    repo = ProjectRepository(db_session)

    projects = await repo.list_by_user(user.id)

    assert [p.name for p in projects] == ["newest", "middle", "oldest"]


async def test_list_by_user_applies_limit_and_offset(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    for i in range(5):
        await ProjectFactory.create(
            user=user, name=f"p{i}", updated_at=_BASE + timedelta(hours=i)
        )
    repo = ProjectRepository(db_session)

    page = await repo.list_by_user(user.id, limit=2, offset=1)

    # Descending by updated_at: p4, p3, p2, p1, p0 → offset 1, limit 2 → p3, p2.
    assert [p.name for p in page] == ["p3", "p2"]


async def test_list_by_user_excludes_other_users_projects(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    await ProjectFactory.create(user=owner, name="mine")
    await ProjectFactory.create(user=other, name="theirs")
    repo = ProjectRepository(db_session)

    projects = await repo.list_by_user(owner.id)

    assert [p.name for p in projects] == ["mine"]


async def test_count_by_user_counts_only_own_projects(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    await ProjectFactory.create(user=owner)
    await ProjectFactory.create(user=owner)
    await ProjectFactory.create(user=other)
    repo = ProjectRepository(db_session)

    assert await repo.count_by_user(owner.id) == 2
    assert await repo.count_by_user(other.id) == 1


async def test_update_changes_name_and_persists(db_session: AsyncSession) -> None:
    project = await ProjectFactory.create(name="Before")
    repo = ProjectRepository(db_session)

    await repo.update(project, name="After")
    refetched = await repo.get_by_id(project.id)

    assert refetched is not None
    assert refetched.name == "After"


async def test_delete_removes_row(db_session: AsyncSession) -> None:
    project = await ProjectFactory.create()
    repo = ProjectRepository(db_session)

    await repo.delete(project)

    assert await repo.get_by_id(project.id) is None
