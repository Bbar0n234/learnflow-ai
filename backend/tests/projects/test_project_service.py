"""ProjectService — sociable-unit tests against in-memory fake repositories.

Asserts the observable result (returned objects, raised branches, store state),
not which collaborator methods fired.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import cast

import pytest
from app.models.project import Project
from app.repositories.mcp_server import MCPServerRepository
from app.repositories.project import ProjectRepository
from app.services.exceptions import EntityNotFoundError
from app.services.project import ProjectService
from app.storage.workspace import Workspace

from tests.projects.fakes import FakeMCPServerRepository, FakeProjectRepository

pytestmark = pytest.mark.unit


def _build_service(
    project_repo: FakeProjectRepository | None = None,
    mcp_repo: FakeMCPServerRepository | None = None,
) -> tuple[ProjectService, FakeProjectRepository, FakeMCPServerRepository]:
    project_repo = project_repo or FakeProjectRepository()
    mcp_repo = mcp_repo or FakeMCPServerRepository()
    service = ProjectService(
        project_repo=cast(ProjectRepository, project_repo),
        mcp_server_repo=cast(MCPServerRepository, mcp_repo),
    )
    return service, project_repo, mcp_repo


async def test_create_project_persists_and_returns_named_project() -> None:
    service, repo, _ = _build_service()
    user_id = uuid.uuid4()

    project = await service.create_project(user_id=user_id, name="Quantum")

    assert project.name == "Quantum"
    assert project.user_id == user_id
    assert repo.projects[project.id] is project


async def test_get_project_returns_existing_project() -> None:
    service, repo, _ = _build_service()
    stored = Project(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Stored")
    repo._add(stored)

    assert await service.get_project(stored.id) is stored


async def test_get_project_missing_raises_entity_not_found() -> None:
    service, _, _ = _build_service()

    with pytest.raises(EntityNotFoundError):
        await service.get_project(uuid.uuid4())


async def test_list_projects_returns_items_and_total() -> None:
    service, repo, _ = _build_service()
    user_id = uuid.uuid4()
    repo._add(Project(id=uuid.uuid4(), user_id=user_id, name="A"))
    repo._add(Project(id=uuid.uuid4(), user_id=user_id, name="B"))
    repo._add(Project(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Other"))

    items, total = await service.list_projects(user_id)

    assert total == 2
    assert {p.name for p in items} == {"A", "B"}


async def test_update_project_changes_name() -> None:
    service, repo, _ = _build_service()
    stored = Project(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Old")
    repo._add(stored)

    updated = await service.update_project(stored.id, name="New")

    assert updated.name == "New"
    assert repo.projects[stored.id].name == "New"


async def test_update_project_missing_raises_entity_not_found() -> None:
    service, _, _ = _build_service()

    with pytest.raises(EntityNotFoundError):
        await service.update_project(uuid.uuid4(), name="X")


async def test_delete_project_removes_it_and_cleans_disables() -> None:
    service, repo, mcp_repo = _build_service()
    stored = Project(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Doomed")
    repo._add(stored)

    await service.delete_project(stored.id)

    assert stored.id not in repo.projects
    assert mcp_repo.cleaned_projects == [stored.id]


async def test_delete_project_missing_raises_entity_not_found() -> None:
    service, _, mcp_repo = _build_service()

    with pytest.raises(EntityNotFoundError):
        await service.delete_project(uuid.uuid4())

    assert mcp_repo.cleaned_projects == []


async def test_delete_project_also_removes_its_workspace_directory(
    tmp_path: Path,
) -> None:
    """Deleting a project takes its files with it (ADR-032 § Lifecycle).

    Artifacts used to disappear by DB cascade; they are files now, so the same
    guarantee has to be made explicitly — otherwise a deleted project keeps
    occupying the shared volume forever (there is no retention job).
    """
    workspaces_root = tmp_path / "workspaces"
    workspaces_root.mkdir()
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    workspace = Workspace(
        workspaces_root=workspaces_root,
        skills_root=skills_root,
        read_limit_chars=1000,
        diff_file_limit_bytes=1000,
        diff_total_limit_bytes=1000,
    )
    service, repo, _ = _build_service()
    stored = Project(id=uuid.uuid4(), user_id=uuid.uuid4(), name="Doomed")
    repo._add(stored)
    workspace.write_text(str(stored.id), "artifacts/notes.md", "x")
    service = ProjectService(
        project_repo=cast(ProjectRepository, repo),
        mcp_server_repo=cast(MCPServerRepository, FakeMCPServerRepository()),
        workspace=workspace,
    )

    await service.delete_project(stored.id)

    assert stored.id not in repo.projects
    assert not (workspaces_root / str(stored.id)).exists()
