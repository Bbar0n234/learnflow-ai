"""RefreshTokenRepository against real Postgres (transactional rollback).

Verifies the SQL behaviour itself: lookup by hash, single-token revoke,
fan-out revoke-all scoped to one user, and expired-token cleanup.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from learnflow_testing.factories import UserFactory
from sqlalchemy.ext.asyncio import AsyncSession


def _token(
    user_id: object,
    token_hash: str,
    *,
    expires_in_days: int = 30,
    revoked: bool = False,
) -> RefreshToken:
    return RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
        revoked_at=datetime.now(UTC) if revoked else None,
    )


@pytest.mark.integration
async def test_create_then_get_by_hash_returns_row(db_session: AsyncSession) -> None:
    user: User = await UserFactory.create()
    repo = RefreshTokenRepository(db_session)

    created = await repo.create(_token(user.id, "hash-create"))
    fetched = await repo.get_by_hash("hash-create")

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.user_id == user.id
    assert fetched.revoked_at is None


@pytest.mark.integration
async def test_get_by_hash_unknown_returns_none(db_session: AsyncSession) -> None:
    repo = RefreshTokenRepository(db_session)

    assert await repo.get_by_hash("no-such-hash") is None


@pytest.mark.integration
async def test_revoke_sets_revoked_at(db_session: AsyncSession) -> None:
    user: User = await UserFactory.create()
    repo = RefreshTokenRepository(db_session)
    created = await repo.create(_token(user.id, "hash-revoke"))

    await repo.revoke(created.id)
    db_session.expire_all()
    fetched = await repo.get_by_hash("hash-revoke")

    assert fetched is not None
    assert fetched.revoked_at is not None


@pytest.mark.integration
async def test_revoke_all_for_user_scoped_to_that_user(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    repo = RefreshTokenRepository(db_session)
    await repo.create(_token(owner.id, "owner-active"))
    await repo.create(_token(other.id, "other-active"))

    await repo.revoke_all_for_user(owner.id)
    db_session.expire_all()

    owner_token = await repo.get_by_hash("owner-active")
    other_token = await repo.get_by_hash("other-active")
    assert owner_token is not None and owner_token.revoked_at is not None
    assert other_token is not None and other_token.revoked_at is None


@pytest.mark.integration
async def test_delete_expired_for_user_removes_only_expired_of_that_user(
    db_session: AsyncSession,
) -> None:
    owner: User = await UserFactory.create()
    other: User = await UserFactory.create()
    repo = RefreshTokenRepository(db_session)
    await repo.create(_token(owner.id, "owner-expired", expires_in_days=-1))
    await repo.create(_token(owner.id, "owner-valid", expires_in_days=30))
    await repo.create(_token(other.id, "other-expired", expires_in_days=-1))

    await repo.delete_expired_for_user(owner.id)

    assert await repo.get_by_hash("owner-expired") is None
    assert await repo.get_by_hash("owner-valid") is not None
    assert await repo.get_by_hash("other-expired") is not None
