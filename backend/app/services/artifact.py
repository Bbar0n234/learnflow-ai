from __future__ import annotations

import uuid

from app.models.artifact import Artifact
from app.repositories.artifact import ArtifactRepository
from app.services.exceptions import EntityNotFoundError


class ArtifactService:
    def __init__(self, *, artifact_repo: ArtifactRepository) -> None:
        self._artifact_repo = artifact_repo

    async def get_artifact(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = await self._artifact_repo.get_by_id(artifact_id)
        if artifact is None:
            raise EntityNotFoundError("Artifact", artifact_id)
        return artifact

    async def list_artifacts(self, project_id: uuid.UUID) -> list[Artifact]:
        return await self._artifact_repo.list_by_project(project_id)
