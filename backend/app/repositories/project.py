from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, user_id: uuid.UUID, name: str) -> Project:
        project = Project(user_id=user_id, name=name)
        self._session.add(project)
        await self._session.flush()
        return project

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def list_by_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Project]:
        result = await self._session.execute(
            select(Project)
            .where(Project.user_id == user_id)
            .order_by(Project.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Project).where(Project.user_id == user_id)
        )
        return result.scalar_one()

    async def update(self, project: Project, *, name: str) -> Project:
        project.name = name
        await self._session.flush()
        await self._session.refresh(project)
        return project

    async def delete(self, project: Project) -> None:
        await self._session.delete(project)
        await self._session.flush()
