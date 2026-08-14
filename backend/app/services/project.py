from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.repositories.mcp_server import MCPServerRepository
from app.repositories.project import ProjectRepository
from app.services.exceptions import EntityNotFoundError
from app.storage.workspace import Workspace


class ProjectService:
    def __init__(
        self,
        *,
        project_repo: ProjectRepository,
        mcp_server_repo: MCPServerRepository,
        workspace: Workspace | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._mcp_server_repo = mcp_server_repo
        # Optional with a None default: ASGI tests build the app without
        # running the lifespan, so `app.state.workspace` never exists there
        # (mirrors `ChatService.title_generator`'s same accommodation).
        self._workspace = workspace
        # Optional, same reasoning as `ChatService._session` (sociable-unit
        # tests construct this service with fake repositories, no DB): used
        # only to commit the row delete explicitly before the workspace
        # directory comes down, mirroring `ChatService.delete_chat`'s
        # "DB transaction first, best-effort file side effect after" order.
        self._session = session

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
        """Delete a project row, then its workspace directory tree.

        Order matters (mirrors `ChatService.delete_chat`): the DB delete is
        committed explicitly here rather than left to the request's
        yield-dependency commit, because that commit only runs *after* this
        method returns — a rollback past this point would otherwise leave the
        row gone from disk (row rolled back, workspace already wiped) or,
        worse, the row still live over an already-deleted workspace. The
        directory removal itself runs off the event loop (`shutil.rmtree`
        over a potentially large tree) via `asyncio.to_thread`.
        """
        project = await self.get_project(project_id)
        await self._mcp_server_repo.cleanup_disables_for_project(project_id)
        await self._project_repo.delete(project)
        if self._session is not None:
            await self._session.commit()
        if self._workspace is not None:
            await asyncio.to_thread(self._workspace.delete_project, str(project_id))
