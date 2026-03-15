from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact import Artifact


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        title: str,
        type: str,
        content: str,
        thread_id: uuid.UUID | None = None,
    ) -> Artifact:
        artifact = Artifact(
            project_id=project_id,
            title=title,
            type=type,
            content=content,
            thread_id=thread_id,
        )
        self._session.add(artifact)
        await self._session.flush()
        return artifact

    async def get_by_id(self, artifact_id: uuid.UUID) -> Artifact | None:
        return await self._session.get(Artifact, artifact_id)

    async def list_by_project(self, project_id: uuid.UUID) -> list[Artifact]:
        result = await self._session.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.created_at.desc())
        )
        return list(result.scalars().all())

    async def set_message_id(
        self, artifact_ids: list[uuid.UUID], message_id: str
    ) -> None:
        """Post-hoc: link artifacts to the final assistant message."""
        await self._session.execute(
            update(Artifact)
            .where(Artifact.id.in_(artifact_ids))
            .values(message_id=message_id)
        )
        await self._session.flush()

    async def list_by_thread(self, thread_id: uuid.UUID) -> list[Artifact]:
        result = await self._session.execute(
            select(Artifact)
            .where(Artifact.thread_id == thread_id)
            .order_by(Artifact.created_at)
        )
        return list(result.scalars().all())

    async def delete(self, artifact: Artifact) -> None:
        await self._session.delete(artifact)
        await self._session.flush()
