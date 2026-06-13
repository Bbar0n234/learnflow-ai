from __future__ import annotations

import uuid

from app.models.project import Project
from app.repositories.project import ProjectRepository
from app.services.exceptions import EntityNotFoundError


class ProjectService:
    def __init__(self, *, project_repo: ProjectRepository) -> None:
        self._project_repo = project_repo

    async def create_project(self, *, user_id: uuid.UUID, name: str) -> Project:
        return await self._project_repo.create(user_id=user_id, name=name)

    async def get_project(self, project_id: uuid.UUID) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise EntityNotFoundError("Project", project_id)
        return project

    async def list_projects(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[Project], int]:
        items = await self._project_repo.list_by_user(
            user_id, limit=limit, offset=offset
        )
        total = await self._project_repo.count_by_user(user_id)
        return items, total

    async def update_project(self, project_id: uuid.UUID, *, name: str) -> Project:
        project = await self.get_project(project_id)
        return await self._project_repo.update(project, name=name)

    async def delete_project(self, project_id: uuid.UUID) -> None:
        project = await self.get_project(project_id)
        await self._project_repo.delete(project)
