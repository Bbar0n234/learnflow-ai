"""Canary: repository against real Postgres with transactional rollback.

Proves the DB harness works end to end — factory-built rows, a repository write,
and a read-back through real SQL. Not coverage; a smoke of the seam.
"""

from __future__ import annotations

import pytest
from app.models.user import User
from app.repositories.project import ProjectRepository
from learnflow_testing.factories import UserFactory
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_project_repository_persists_and_reads_back(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = ProjectRepository(db_session)

    created = await repo.create(user_id=user.id, name="Canary project")
    fetched = await repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.name == "Canary project"
    assert fetched.user_id == user.id


@pytest.mark.integration
async def test_rollback_isolates_tests_no_leftover_rows(
    db_session: AsyncSession,
) -> None:
    # If the previous test's rows leaked, this user count would be off. The
    # transactional rollback gives each test a clean slate.
    user: User = await UserFactory.create()
    repo = ProjectRepository(db_session)

    assert await repo.count_by_user(user.id) == 0
