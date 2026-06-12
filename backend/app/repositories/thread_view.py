from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.models.project import Project
from app.models.thread_view import ThreadView


class ThreadViewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, project_id: uuid.UUID, title: str) -> ThreadView:
        thread_view = ThreadView(project_id=project_id, title=title)
        self._session.add(thread_view)
        await self._session.flush()
        return thread_view

    async def get_by_id(self, thread_id: uuid.UUID) -> ThreadView | None:
        return await self._session.get(ThreadView, thread_id)

    async def list_by_project(
        self, project_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[ThreadView]:
        result = await self._session.execute(
            select(ThreadView)
            .where(ThreadView.project_id == project_id)
            .order_by(ThreadView.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ThreadView)
            .where(ThreadView.project_id == project_id)
        )
        return result.scalar_one()

    async def list_recent(
        self, user_id: uuid.UUID, *, limit: int = 10, offset: int = 0
    ) -> list[ThreadView]:
        result = await self._session.execute(
            select(ThreadView)
            .join(ThreadView.project)
            .where(Project.user_id == user_id)
            .options(contains_eager(ThreadView.project))
            .order_by(ThreadView.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().unique().all())

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(ThreadView)
            .join(ThreadView.project)
            .where(Project.user_id == user_id)
        )
        return result.scalar_one()

    async def update(self, thread_view: ThreadView, *, title: str) -> ThreadView:
        thread_view.title = title
        await self._session.flush()
        await self._session.refresh(thread_view)
        return thread_view

    async def touch(self, thread_view: ThreadView) -> None:
        """Update updated_at without changing other fields."""
        thread_view.title = thread_view.title  # mark dirty to trigger onupdate
        await self._session.flush()
        await self._session.refresh(thread_view)

    async def delete(self, thread_view: ThreadView) -> None:
        await self._session.delete(thread_view)
        await self._session.flush()

    async def mark_security_blocked(self, thread_id: uuid.UUID) -> None:
        await self._session.execute(
            update(ThreadView)
            .where(ThreadView.thread_id == thread_id)
            .values(security_blocked=True)
        )
        await self._session.flush()

    async def is_security_blocked(self, thread_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ThreadView.security_blocked).where(ThreadView.thread_id == thread_id)
        )
        row = result.first()
        return bool(row[0]) if row is not None else False
