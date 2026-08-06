"""Integration tests for ``SettingsRepository`` against real Postgres.

Settings rows use JSONB (``extra_body``) and FK-bound primary keys (user /
project / thread). We exercise the SQL directly — upsert-create, upsert-update,
and the absent-row read — on the transactional session that rolls back per test.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.settings import SettingsRepository
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_get_user_settings_absent_returns_none(
    db_session: AsyncSession,
) -> None:
    repo = SettingsRepository(db_session)

    assert await repo.get_user_settings(uuid.uuid4()) is None


@pytest.mark.integration
async def test_upsert_user_settings_creates_then_reads_back(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = SettingsRepository(db_session)

    await repo.upsert_user_settings(
        user.id, model_name="gpt-4o", extra_body={"temperature": 0.2}
    )
    fetched = await repo.get_user_settings(user.id)

    assert fetched is not None
    assert fetched.model_name == "gpt-4o"
    assert fetched.extra_body == {"temperature": 0.2}


@pytest.mark.integration
async def test_upsert_user_settings_updates_existing_row(
    db_session: AsyncSession,
) -> None:
    user: User = await UserFactory.create()
    repo = SettingsRepository(db_session)
    await repo.upsert_user_settings(user.id, model_name="gpt-4o", extra_body=None)

    updated = await repo.upsert_user_settings(
        user.id, model_name="claude-3", extra_body={"k": 1}
    )

    assert updated.model_name == "claude-3"
    assert updated.extra_body == {"k": 1}
    # Still a single row keyed by user_id (upsert, not insert).
    again = await repo.get_user_settings(user.id)
    assert again is not None
    assert again.model_name == "claude-3"


@pytest.mark.integration
async def test_upsert_project_settings_round_trips(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    repo = SettingsRepository(db_session)

    await repo.upsert_project_settings(project.id, model_name="proj-model")
    fetched = await repo.get_project_settings(project.id)

    assert fetched is not None
    assert fetched.model_name == "proj-model"


@pytest.mark.integration
async def test_upsert_thread_settings_round_trips(
    db_session: AsyncSession,
) -> None:
    project = await ProjectFactory.create()
    thread = ThreadView(project_id=project.id, title="t")
    db_session.add(thread)
    await db_session.flush()
    repo = SettingsRepository(db_session)

    await repo.upsert_thread_settings(thread.thread_id, model_name="thread-model")
    fetched = await repo.get_thread_settings(thread.thread_id)

    assert fetched is not None
    assert fetched.model_name == "thread-model"
