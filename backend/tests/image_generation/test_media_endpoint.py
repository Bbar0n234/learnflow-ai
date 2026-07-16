"""Media endpoint — integration through the authenticated ASGI client (T1.3).

``GET /projects/{project_id}/artifacts/{artifact_id}/media`` serves raw image
bytes under JWT with an immutable cache header. Contract under test: 200 with the
blob's ``Content-Type`` + ``Cache-Control: private, max-age=31536000, immutable``;
404 when the blob is absent, the artifact belongs to another project, the project
belongs to another user, or the artifact does not exist. Auth itself is covered
by the auth suite — here the client is already authenticated.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.user import User
from app.repositories.artifact import ArtifactRepository
from app.storage.blob_storage import PgBlobStorage
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.projects._builders import create_other_project, create_owned_project

pytestmark = pytest.mark.integration

_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(120))


async def _image_artifact(
    session: AsyncSession, project_id: uuid.UUID, *, with_blob: bool = True
) -> uuid.UUID:
    artifact = await ArtifactRepository(session).create(
        project_id=project_id, title="Cover", type="image", content="a prompt"
    )
    if with_blob:
        await PgBlobStorage(session).put(
            artifact_id=artifact.id, data=_PNG, mime_type="image/png"
        )
    return artifact.id


async def test_media_returns_bytes_mime_and_immutable_cache(
    client: AsyncClient, current_user: User, db_session: AsyncSession
) -> None:
    project = await create_owned_project(current_user)
    artifact_id = await _image_artifact(db_session, project.id)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/media"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == _PNG
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"


async def test_media_without_blob_returns_404(
    client: AsyncClient, current_user: User, db_session: AsyncSession
) -> None:
    project = await create_owned_project(current_user)
    artifact_id = await _image_artifact(db_session, project.id, with_blob=False)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/media"
    )

    assert response.status_code == 404


async def test_media_missing_artifact_returns_404(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{uuid.uuid4()}/media"
    )

    assert response.status_code == 404


async def test_media_for_artifact_in_another_project_returns_404(
    client: AsyncClient, current_user: User, db_session: AsyncSession
) -> None:
    project_a = await create_owned_project(current_user)
    project_b = await create_owned_project(current_user)
    artifact_id = await _image_artifact(db_session, project_b.id)

    response = await client.get(
        f"/api/projects/{project_a.id}/artifacts/{artifact_id}/media"
    )

    assert response.status_code == 404


async def test_media_under_other_users_project_returns_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    project = await create_other_project()
    artifact_id = await _image_artifact(db_session, project.id)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact_id}/media"
    )

    assert response.status_code == 404
