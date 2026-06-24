"""In-memory fakes for sociable-unit service tests (S4).

Working ``dict``-backed stands-in for the repositories the project/artifact
services collaborate with. They speak the same duck-typed interface as the real
repositories, so the service runs its real logic; tests assert the *result*
(returned objects, raised branches), not which methods were called.
"""

from __future__ import annotations

import uuid

from app.models.artifact import Artifact
from app.models.project import Project


class FakeProjectRepository:
    def __init__(self) -> None:
        self.projects: dict[uuid.UUID, Project] = {}

    def _add(self, project: Project) -> None:
        self.projects[project.id] = project

    async def create(self, *, user_id: uuid.UUID, name: str) -> Project:
        project = Project(id=uuid.uuid4(), user_id=user_id, name=name)
        self.projects[project.id] = project
        return project

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        return self.projects.get(project_id)

    async def list_by_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Project]:
        items = [p for p in self.projects.values() if p.user_id == user_id]
        return items[offset : offset + limit]

    async def count_by_user(self, user_id: uuid.UUID) -> int:
        return len([p for p in self.projects.values() if p.user_id == user_id])

    async def update(self, project: Project, *, name: str) -> Project:
        project.name = name
        return project

    async def delete(self, project: Project) -> None:
        self.projects.pop(project.id, None)


class FakeMCPServerRepository:
    """Records the projects whose disables were cleaned up."""

    def __init__(self) -> None:
        self.cleaned_projects: list[uuid.UUID] = []

    async def cleanup_disables_for_project(self, project_id: uuid.UUID) -> None:
        self.cleaned_projects.append(project_id)


class FakeArtifactRepository:
    def __init__(self) -> None:
        self.artifacts: dict[uuid.UUID, Artifact] = {}

    def _add(self, artifact: Artifact) -> None:
        self.artifacts[artifact.id] = artifact

    async def get_by_id(self, artifact_id: uuid.UUID) -> Artifact | None:
        return self.artifacts.get(artifact_id)

    async def list_by_project(
        self, project_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Artifact]:
        items = [a for a in self.artifacts.values() if a.project_id == project_id]
        return items[offset : offset + limit]

    async def count_by_project(self, project_id: uuid.UUID) -> int:
        return len([a for a in self.artifacts.values() if a.project_id == project_id])

    async def list_by_thread(self, thread_id: uuid.UUID) -> list[Artifact]:
        return [a for a in self.artifacts.values() if a.thread_id == thread_id]
