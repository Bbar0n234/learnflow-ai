"""UserRepository against real Postgres (transactional rollback)."""

from __future__ import annotations

import uuid

import pytest
from app.models.user import User
from app.repositories.user import UserRepository
from learnflow_testing.factories import UserFactory
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_get_by_name_returns_matching_user(db_session: AsyncSession) -> None:
    await UserFactory.create(name="findme")
    repo = UserRepository(db_session)

    found = await repo.get_by_name("findme")

    assert found is not None
    assert found.name == "findme"


@pytest.mark.integration
async def test_get_by_name_unknown_returns_none(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    assert await repo.get_by_name("ghost") is None


@pytest.mark.integration
async def test_get_by_id_unknown_returns_none(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    assert await repo.get_by_id(uuid.uuid4()) is None


@pytest.mark.integration
async def test_create_persists_and_reads_back(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    created = await repo.create(User(name="fresh", password_hash="hash"))
    fetched = await repo.get_by_id(created.id)

    assert fetched is not None
    assert fetched.name == "fresh"


@pytest.mark.integration
async def test_create_duplicate_name_violates_unique_constraint(
    db_session: AsyncSession,
) -> None:
    repo = UserRepository(db_session)
    await repo.create(User(name="taken", password_hash="hash"))

    with pytest.raises(IntegrityError):
        await repo.create(User(name="taken", password_hash="hash2"))
