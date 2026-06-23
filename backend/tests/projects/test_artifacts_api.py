"""Artifacts HTTP handlers — integration through the authenticated ASGI client.

Covers listing, detail, markdown and PDF download, the cross-project 404 guard,
project ownership, and validation. The real wkhtmltopdf binary and the
lifespan-populated ``app.state.settings`` are absent under ASGITransport (see
conftest ``app`` docstring), so the PDF test stubs ``convert_md_to_pdf`` and
injects the one setting the handler reads.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.models.user import User
from fastapi import FastAPI
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
    # List items are the lightweight projection — no heavy ``content`` field
    # (that is detail-only). Catches a leak of the full markdown into the list.
    assert all("content" not in item for item in body["items"])


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
    disposition = response.headers["content-disposition"]
    assert "attachment" in disposition
    # Filename derives from the artifact title with a ``.md`` suffix (RFC 5987
    # ``filename*`` form). A regression that lost the title or extension shows
    # up here, not just in a bare "attachment" check.
    assert "filename*=UTF-8''Report.md" in disposition
    assert response.text == "# Body"


async def test_download_artifact_defaults_to_markdown_without_format(
    client: AsyncClient, current_user: User
) -> None:
    """No ``format`` query → markdown branch (the handler default)."""
    project = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(
        project=project, title="Plain", content="# Default"
    )

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}/download"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "filename*=UTF-8''Plain.md" in response.headers["content-disposition"]
    assert response.text == "# Default"


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
    # The pattern-constraint rejection must surface as RFC 9457 problem+json,
    # not FastAPI's raw ``{"detail": [...]}`` — the app installs a custom
    # validation handler and the contract is the project-wide envelope.
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:learnflow:validation-error"
    assert body["status"] == 422
    # The narrowed error list pins the offending location (the ``format`` query).
    assert any(err["loc"][-1] == "format" for err in body["errors"])


async def test_download_pdf_branch_converts_via_export(
    client: AsyncClient,
    current_user: User,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``format=pdf`` routes through ``convert_md_to_pdf`` and returns the bytes.

    The real wkhtmltopdf binary and lifespan-populated ``app.state.settings`` are
    absent under ASGITransport, so we stub the converter and inject the one
    setting the handler reads (``pdf_conversion_timeout_seconds``).
    """
    project = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(
        project=project, title="Export", content="# Source"
    )

    captured: dict[str, object] = {}

    def _fake_convert(content: str, timeout: int = 30) -> bytes:
        captured["content"] = content
        captured["timeout"] = timeout
        return b"%PDF-1.4 fake-bytes"

    app.state.settings = SimpleNamespace(pdf_conversion_timeout_seconds=42)
    monkeypatch.setattr("app.api.routes.artifacts.convert_md_to_pdf", _fake_convert)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}/download",
        params={"format": "pdf"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''Export.pdf" in response.headers["content-disposition"]
    assert response.content == b"%PDF-1.4 fake-bytes"
    # The artifact's markdown was handed to the converter with the injected
    # timeout — proves the handler wires content and settings through, not a
    # hard-coded default.
    assert captured == {"content": "# Source", "timeout": 42}


async def test_download_artifact_from_another_project_returns_404(
    client: AsyncClient, current_user: User
) -> None:
    """The ``/download`` ownership guard (its own check) rejects cross-project."""
    project_a = await create_owned_project(current_user)
    project_b = await create_owned_project(current_user)
    artifact = await ArtifactFactory.create(project=project_b)

    response = await client.get(
        f"/api/projects/{project_a.id}/artifacts/{artifact.id}/download"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Artifact not found"


async def test_download_artifact_under_other_users_project_returns_404(
    client: AsyncClient,
) -> None:
    """An artifact under another user's project is not downloadable (404)."""
    project = await create_other_project()
    artifact = await ArtifactFactory.create(project=project)

    response = await client.get(
        f"/api/projects/{project.id}/artifacts/{artifact.id}/download"
    )

    assert response.status_code == 404
