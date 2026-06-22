"""Artifacts HTTP handlers — integration through the authenticated ASGI client.

Covers listing, detail, markdown download, the cross-project 404 guard, project
ownership, and validation. The PDF download path is not covered here: it needs
the wkhtmltopdf binary plus ``app.state.settings`` populated by lifespan, which
ASGITransport does not run (see conftest ``app`` docstring).
"""

from __future__ import annotations

import uuid

import pytest
from app.models.user import User
from httpx import AsyncClient

from tests.projects._builders import create_other_project, create_owned_project
from tests.projects.conftest import ArtifactFactory

pytestmark = pytest.mark.integration


async def test_list_artifacts_returns_envelope_for_owned_project(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)
    await ArtifactFactory.create(project=project, title="One")
    await ArtifactFactory.create(project=project, title="Two")

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["title"] for item in body["items"]} == {"One", "Two"}
    assert body["limit"] == 50 and body["offset"] == 0


async def test_list_artifacts_for_other_users_project_returns_404(
    client: AsyncClient,
) -> None:
    project = await create_other_project()

    response = await client.get(f"/api/projects/{project.id}/artifacts")

    assert response.status_code == 404


async def test_get_artifact_returns_detail_with_content(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(
        project=project, title="Notes", content="# Heading"
    )

    response = await client.get(f"/api/projects/{project.id}/artifacts/{artifact.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Notes"
    assert body["content"] == "# Heading"


async def test_get_artifact_missing_returns_404_entity_not_found(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)

    response = await client.get(f"/api/projects/{project.id}/artifacts/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["type"] == "urn:learnflow:entity-not-found"


async def test_get_artifact_from_another_project_returns_404(
    client: AsyncClient, current_user: User
) -> None:
    project_a = await create_owned_project(current_user)
    project_b = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(project=project_b)

    response = await client.get(f"/api/projects/{project_a.id}/artifacts/{artifact.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


async def test_get_artifact_under_other_users_project_returns_404(
    client: AsyncClient,
) -> None:
    project = await create_other_project()
    artifact = await ArtifactFactory.create(project=project)

    response = await client.get(f"/api/projects/{project.id}/artifacts/{artifact.id}")

    assert response.status_code == 404


async def test_download_artifact_as_markdown_returns_file(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(
        project=project, title="Report", content="# Body"
    )

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}/download",
        params={"format": "md"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text == "# Body"


async def test_download_artifact_invalid_format_returns_422(
    client: AsyncClient, current_user: User
) -> None:
    project = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(project=project)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}/download",
        params={"format": "txt"},
    )

    assert response.status_code == 422
