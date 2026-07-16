from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_blob import ArtifactBlob


class BlobStorage(Protocol):
    async def put(
        self, *, artifact_id: uuid.UUID, data: bytes, mime_type: str
    ) -> None: ...

    async def get(self, artifact_id: uuid.UUID) -> tuple[bytes, str] | None: ...

    async def delete(self, artifact_id: uuid.UUID) -> None: ...


class PgBlobStorage:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, *, artifact_id: uuid.UUID, data: bytes, mime_type: str) -> None:
        blob = ArtifactBlob(artifact_id=artifact_id, data=data, mime_type=mime_type)
        self._session.add(blob)
        await self._session.flush()

    async def get(self, artifact_id: uuid.UUID) -> tuple[bytes, str] | None:
        result = await self._session.execute(
            select(ArtifactBlob.data, ArtifactBlob.mime_type).where(
                ArtifactBlob.artifact_id == artifact_id
            )
        )
        row = result.first()
        if row is None:
            return None
        return row.data, row.mime_type

    async def delete(self, artifact_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(ArtifactBlob).where(ArtifactBlob.artifact_id == artifact_id)
        )
        await self._session.flush()
