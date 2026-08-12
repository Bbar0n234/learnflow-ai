"""Uploads REST — integration through the authenticated ASGI client.

`POST /projects/{id}/uploads` is the single write endpoint of the file model
and the whole ingestion story for attachments: the file lands in the project's
`uploads/` zone and the agent reads it back later with its own tools. What the
suite pins is the part a client controls and therefore cannot be trusted with
— the filename. It must reduce to a safe basename (no directories can be
conjured out of it), and a repeat must never overwrite the file an older
message's metadata still points at. Size is the other client-controlled
dimension: over the limit the request has to fail as a well-formed 413, not as
a 500 after the body already sat in memory.

Ownership is real (Postgres), the workspace is a real directory tree; only the
size limit is dialled down through `app.state.settings` so the oversized case
costs bytes rather than megabytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.config import Settings
from app.models.user import User
from app.storage.workspace import Workspace
from fastapi import FastAPI
from httpx import AsyncClient

from tests.projects._builders import create_other_project, create_owned_project

pytestmark = pytest.mark.integration

_LIMIT_BYTES = 64


@pytest.fixture(autouse=True)
def upload_settings(app: FastAPI) -> Settings:
    """Settings on ``app.state`` (lifespan never runs here), with a tiny limit."""
    settings = Settings(upload_max_size_bytes=_LIMIT_BYTES)
    app.state.settings = settings
    return settings


async def test_upload_stores_the_file_and_returns_its_workspace_path(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)

    response = await client.post(
        f"/api/projects/{project.id}/uploads",
        files={"file": ("lecture.md", b"# Notes", "text/markdown")},
    )

    assert response.status_code == 201
    assert response.json() == {"path": "uploads/lecture.md"}
    stored = workspaces_root / str(project.id) / "uploads" / "lecture.md"
    assert stored.read_bytes() == b"# Notes"


async def test_uploading_the_same_name_twice_keeps_both_files(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    # An older message's attachment metadata still points at the first file —
    # a repeat gets a numeric suffix instead of overwriting it.
    project = await create_owned_project(current_user)
    url = f"/api/projects/{project.id}/uploads"
    await client.post(url, files={"file": ("lecture.pdf", b"first", "text/plain")})

    second = await client.post(
        url, files={"file": ("lecture.pdf", b"second", "text/plain")}
    )

    assert second.json() == {"path": "uploads/lecture-1.pdf"}
    uploads = workspaces_root / str(project.id) / "uploads"
    assert (uploads / "lecture.pdf").read_bytes() == b"first"
    assert (uploads / "lecture-1.pdf").read_bytes() == b"second"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        pytest.param("../../etc/passwd", "uploads/passwd", id="posix-traversal"),
        pytest.param("C:\\Users\\me\\notes.txt", "uploads/notes.txt", id="windows"),
        pytest.param("Лекция №1.md", "uploads/Лекция №1.md", id="cyrillic-kept"),
    ],
)
async def test_upload_reduces_the_client_filename_to_a_safe_basename(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
    filename: str,
    expected: str,
) -> None:
    project = await create_owned_project(current_user)

    response = await client.post(
        f"/api/projects/{project.id}/uploads",
        files={"file": (filename, b"payload", "text/plain")},
    )

    assert response.json() == {"path": expected}
    uploads = workspaces_root / str(project.id) / "uploads"
    assert [p.name for p in uploads.iterdir()] == [expected.removeprefix("uploads/")]


async def test_upload_over_the_size_limit_is_413_problem(
    client: AsyncClient,
    current_user: User,
    workspace: Workspace,
    workspaces_root: Path,
) -> None:
    project = await create_owned_project(current_user)

    response = await client.post(
        f"/api/projects/{project.id}/uploads",
        files={"file": ("big.bin", b"x" * (_LIMIT_BYTES + 1), "text/plain")},
    )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"]
    assert not (workspaces_root / str(project.id) / "uploads").exists()


async def test_upload_at_exactly_the_size_limit_is_accepted(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    project = await create_owned_project(current_user)

    response = await client.post(
        f"/api/projects/{project.id}/uploads",
        files={"file": ("edge.bin", b"x" * _LIMIT_BYTES, "text/plain")},
    )

    assert response.status_code == 201


async def test_upload_into_someone_elses_project_is_404(
    client: AsyncClient, workspace: Workspace, workspaces_root: Path
) -> None:
    project = await create_other_project()

    response = await client.post(
        f"/api/projects/{project.id}/uploads",
        files={"file": ("lecture.md", b"# Notes", "text/markdown")},
    )

    assert response.status_code == 404
    assert not (workspaces_root / str(project.id)).exists()


async def test_uploads_are_write_only_over_rest(
    client: AsyncClient, current_user: User, workspace: Workspace
) -> None:
    # v1 has no read of this zone (the history chip renders from message
    # metadata, not by fetching the file back) — only POST is routed.
    project = await create_owned_project(current_user)

    response = await client.get(f"/api/projects/{project.id}/uploads")

    # Whether the router answers 404 or 405 is Starlette's business; what the
    # contract fixes is that no read of this zone is served.
    assert response.status_code in (404, 405)
