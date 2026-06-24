"""ArtifactService — sociable-unit tests against an in-memory fake repository."""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from app.models.artifact import Artifact
from app.repositories.artifact import ArtifactRepository
from app.services.artifact import ArtifactService
from app.services.exceptions import EntityNotFoundError

from tests.projects.fakes import FakeArtifactRepository

pytestmark = pytest.mark.unit


def _build_service() -> tuple[ArtifactService, FakeArtifactRepository]:
    repo = FakeArtifactRepository()
    service = ArtifactService(artifact_repo=cast(ArtifactRepository, repo))
    return service, repo


def _artifact(
    *, project_id: uuid.UUID, thread_id: uuid.UUID | None = None, title: str = "Doc"
) -> Artifact:
    return Artifact(
        id=uuid.uuid4(),
        project_id=project_id,
        thread_id=thread_id,
        title=title,
        type="summary",
        content="body",
    )


async def test_get_artifact_returns_existing() -> None:
    service, repo = _build_service()
    stored = _artifact(project_id=uuid.uuid4())
    repo._add(stored)

    assert await service.get_artifact(stored.id) is stored


async def test_get_artifact_missing_raises_entity_not_found() -> None:
    service, _ = _build_service()

    with pytest.raises(EntityNotFoundError):
        await service.get_artifact(uuid.uuid4())


async def test_list_artifacts_returns_items_and_total() -> None:
    service, repo = _build_service()
    project_id = uuid.uuid4()
    repo._add(_artifact(project_id=project_id, title="A"))
    repo._add(_artifact(project_id=project_id, title="B"))
    repo._add(_artifact(project_id=uuid.uuid4(), title="Other"))

    items, total = await service.list_artifacts(project_id)

    assert total == 2
    assert {a.title for a in items} == {"A", "B"}


async def test_list_by_thread_returns_only_that_threads_artifacts() -> None:
    service, repo = _build_service()
    project_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    repo._add(_artifact(project_id=project_id, thread_id=thread_id, title="In"))
    repo._add(_artifact(project_id=project_id, thread_id=uuid.uuid4(), title="Out"))

    result = await service.list_by_thread(thread_id)

    assert [a.title for a in result] == ["In"]
