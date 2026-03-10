from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class SphereData:
    """Knowledge Sphere of a project."""

    project_id: uuid.UUID
    content: str
    updated_at: datetime


class SphereService(Protocol):
    async def get(self, *, project_id: uuid.UUID) -> SphereData: ...
    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData: ...


class StubSphereService:
    async def get(self, *, project_id: uuid.UUID) -> SphereData:
        return SphereData(
            project_id=project_id,
            content="",
            updated_at=datetime.now(timezone.utc),
        )

    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData:
        return SphereData(
            project_id=project_id,
            content=content,
            updated_at=datetime.now(timezone.utc),
        )
