from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import ProjectSettings, ThreadSettings, UserSettings


class SettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- User ---

    async def get_user_settings(self, user_id: uuid.UUID) -> UserSettings | None:
        return await self._session.get(UserSettings, user_id)

    async def upsert_user_settings(
        self, user_id: uuid.UUID, **kwargs: Any
    ) -> UserSettings:
        settings = await self.get_user_settings(user_id)
        if settings is None:
            settings = UserSettings(user_id=user_id, **kwargs)
            self._session.add(settings)
        else:
            for key, value in kwargs.items():
                setattr(settings, key, value)
        await self._session.flush()
        await self._session.refresh(settings)
        return settings

    # --- Project ---

    async def get_project_settings(
        self, project_id: uuid.UUID
    ) -> ProjectSettings | None:
        return await self._session.get(ProjectSettings, project_id)

    async def upsert_project_settings(
        self, project_id: uuid.UUID, **kwargs: Any
    ) -> ProjectSettings:
        settings = await self.get_project_settings(project_id)
        if settings is None:
            settings = ProjectSettings(project_id=project_id, **kwargs)
            self._session.add(settings)
        else:
            for key, value in kwargs.items():
                setattr(settings, key, value)
        await self._session.flush()
        await self._session.refresh(settings)
        return settings

    # --- Thread ---

    async def get_thread_settings(self, thread_id: uuid.UUID) -> ThreadSettings | None:
        result = await self._session.execute(
            select(ThreadSettings).where(ThreadSettings.thread_id == thread_id)
        )
        return result.scalar_one_or_none()

    async def upsert_thread_settings(
        self, thread_id: uuid.UUID, **kwargs: Any
    ) -> ThreadSettings:
        settings = await self.get_thread_settings(thread_id)
        if settings is None:
            settings = ThreadSettings(thread_id=thread_id, **kwargs)
            self._session.add(settings)
        else:
            for key, value in kwargs.items():
                setattr(settings, key, value)
        await self._session.flush()
        await self._session.refresh(settings)
        return settings
