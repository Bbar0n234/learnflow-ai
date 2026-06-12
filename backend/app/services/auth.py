from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import anyio.to_thread
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.services.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ReplayDetectedError,
    TokenExpiredError,
    UsernameAlreadyExistsError,
)
from app.services.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_raw_token,
    verify_password,
)


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._user_repo = UserRepository(session)
        self._token_repo = RefreshTokenRepository(session)
        self._settings = settings

    async def register(self, name: str, password: str) -> tuple[User, str, str]:
        existing = await self._user_repo.get_by_name(name)
        if existing is not None:
            raise UsernameAlreadyExistsError

        # argon2 — CPU-bound (~сотни мс), уводим из event loop
        password_hash = await anyio.to_thread.run_sync(hash_password, password)
        user = User(name=name, password_hash=password_hash)
        await self._user_repo.create(user)

        access_token = self._create_access(user)
        refresh_raw = await self._create_refresh(user.id)
        return user, access_token, refresh_raw

    async def login(self, name: str, password: str) -> tuple[User, str, str]:
        user = await self._user_repo.get_by_name(name)
        if user is None or not await anyio.to_thread.run_sync(
            verify_password, user.password_hash, password
        ):
            raise InvalidCredentialsError

        access_token = self._create_access(user)
        refresh_raw = await self._create_refresh(user.id)
        return user, access_token, refresh_raw

    async def refresh(self, token_raw: str) -> tuple[str, str]:
        token_hash = hash_raw_token(token_raw)
        stored = await self._token_repo.get_by_hash(token_hash)

        if stored is None:
            raise InvalidTokenError

        if stored.revoked_at is not None:
            await self._token_repo.revoke_all_for_user(stored.user_id)
            raise ReplayDetectedError

        if stored.expires_at < datetime.now(UTC):
            raise TokenExpiredError

        await self._token_repo.revoke(stored.id)

        # Fetch user to get is_admin status
        user = await self._user_repo.get_by_id(stored.user_id)
        if user is None:
            raise InvalidTokenError

        access_token = self._create_access(user)
        refresh_raw = await self._create_refresh(stored.user_id)
        return access_token, refresh_raw

    async def logout(self, token_raw: str) -> None:
        token_hash = hash_raw_token(token_raw)
        stored = await self._token_repo.get_by_hash(token_hash)
        if stored is not None:
            await self._token_repo.revoke(stored.id)

    def _create_access(self, user: User) -> str:
        is_admin = getattr(user, "is_admin", False)
        return create_access_token(
            user.id,
            self._settings.jwt_secret,
            self._settings.access_token_expire_minutes,
            is_admin=is_admin,
        )

    async def _create_refresh(self, user_id: uuid.UUID) -> str:
        raw, token_hash = generate_refresh_token()
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC)
            + timedelta(days=self._settings.refresh_token_expire_days),
        )
        await self._token_repo.create(token)
        return raw
