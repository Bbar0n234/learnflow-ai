from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server import (
    MCPServerDisable,
    ProjectMCPServer,
    ThreadMCPServer,
    UserMCPServer,
)

_SCOPE_MODELS = {
    "user": UserMCPServer,
    "project": ProjectMCPServer,
    "thread": ThreadMCPServer,
}

_SCOPE_FK = {
    "user": "user_id",
    "project": "project_id",
    "thread": "thread_id",
}


class MCPServerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- List ---

    async def list_by_user(
        self, user_id: uuid.UUID, *, active_only: bool = True
    ) -> list[UserMCPServer]:
        stmt = select(UserMCPServer).where(UserMCPServer.user_id == user_id)
        if active_only:
            stmt = stmt.where(UserMCPServer.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(UserMCPServer.created_at))
        return list(result.scalars().all())

    async def list_by_project(
        self, project_id: uuid.UUID, *, active_only: bool = True
    ) -> list[ProjectMCPServer]:
        stmt = select(ProjectMCPServer).where(ProjectMCPServer.project_id == project_id)
        if active_only:
            stmt = stmt.where(ProjectMCPServer.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(ProjectMCPServer.created_at))
        return list(result.scalars().all())

    async def list_by_thread(
        self, thread_id: uuid.UUID, *, active_only: bool = True
    ) -> list[ThreadMCPServer]:
        stmt = select(ThreadMCPServer).where(ThreadMCPServer.thread_id == thread_id)
        if active_only:
            stmt = stmt.where(ThreadMCPServer.is_active.is_(True))
        result = await self._session.execute(stmt.order_by(ThreadMCPServer.created_at))
        return list(result.scalars().all())

    # --- Get by ID (typed) ---

    async def get_user_server(self, server_id: uuid.UUID) -> UserMCPServer | None:
        return await self._session.get(UserMCPServer, server_id)

    async def get_project_server(self, server_id: uuid.UUID) -> ProjectMCPServer | None:
        return await self._session.get(ProjectMCPServer, server_id)

    async def get_thread_server(self, server_id: uuid.UUID) -> ThreadMCPServer | None:
        return await self._session.get(ThreadMCPServer, server_id)

    # --- Create ---

    async def create_user_server(self, **data: Any) -> UserMCPServer:
        server = UserMCPServer(**data)
        self._session.add(server)
        await self._session.flush()
        await self._session.refresh(server)
        return server

    async def create_project_server(self, **data: Any) -> ProjectMCPServer:
        server = ProjectMCPServer(**data)
        self._session.add(server)
        await self._session.flush()
        await self._session.refresh(server)
        return server

    async def create_thread_server(self, **data: Any) -> ThreadMCPServer:
        server = ThreadMCPServer(**data)
        self._session.add(server)
        await self._session.flush()
        await self._session.refresh(server)
        return server

    # --- Update ---

    async def update(self, server: Any, **data: Any) -> Any:
        for key, value in data.items():
            setattr(server, key, value)
        await self._session.flush()
        await self._session.refresh(server)
        return server

    # --- Delete ---

    async def delete(self, server: Any) -> None:
        await self._session.delete(server)
        await self._session.flush()

    # --- Count ---

    async def count_by_scope(self, scope: str, scope_id: uuid.UUID) -> int:
        model = _SCOPE_MODELS[scope]
        fk_col = getattr(model, _SCOPE_FK[scope])
        result = await self._session.execute(
            select(func.count()).select_from(model).where(fk_col == scope_id)
        )
        return result.scalar_one()

    # --- Disables (cascade toggle) ---

    async def list_disabled_ids(
        self, scope_type: str, scope_id: uuid.UUID
    ) -> set[uuid.UUID]:
        result = await self._session.execute(
            select(MCPServerDisable.server_id).where(
                MCPServerDisable.scope_type == scope_type,
                MCPServerDisable.scope_id == scope_id,
            )
        )
        return set(result.scalars().all())

    async def set_disable(
        self,
        scope_type: str,
        scope_id: uuid.UUID,
        server_id: uuid.UUID,
        *,
        disabled: bool,
    ) -> None:
        existing = await self._session.get(
            MCPServerDisable, (scope_type, scope_id, server_id)
        )
        if disabled and existing is None:
            self._session.add(
                MCPServerDisable(
                    scope_type=scope_type,
                    scope_id=scope_id,
                    server_id=server_id,
                )
            )
            await self._session.flush()
        elif not disabled and existing is not None:
            await self._session.delete(existing)
            await self._session.flush()

    async def cleanup_disables_for_server(self, server_id: uuid.UUID) -> None:
        result = await self._session.execute(
            select(MCPServerDisable).where(MCPServerDisable.server_id == server_id)
        )
        for disable in result.scalars().all():
            await self._session.delete(disable)
        await self._session.flush()
