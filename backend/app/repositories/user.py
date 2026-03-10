from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_or_create(self, name: str) -> User:
        stmt = (
            pg_insert(User)
            .values(name=name)
            .on_conflict_do_nothing(index_elements=["name"])
        )
        await self._session.execute(stmt)

        result = await self._session.execute(select(User).where(User.name == name))
        user = result.scalar_one()

        await self._session.flush()
        return user
