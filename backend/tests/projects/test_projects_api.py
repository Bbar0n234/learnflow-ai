"""Projects HTTP handlers — integration through the authenticated ASGI client.

Route -> service -> repository -> real Postgres. Asserts status codes, the list
envelope, the project response shape, ownership 404s, and problem+json error
bodies (norms from doc/tech/conventions/api.md).
"""

from __future__ import annotations

import uuid

import pytest
from app.models.user import User
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_create_project_returns_201_and_body(
    client: AsyncClient, current_user: User
) -> None:
    response = await client.post("/api/projects", json={"name": "Linear Algebra"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Linear Algebra"
    assert uuid.UUID(body["id"])
    assert "created_at" in body and "updated_at" in body


async def test_create_project_missing_name_returns_422_problem(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/projects", json={})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:learnflow:validation-error"
    assert isinstance(body["errors"], list)


async def test_list_projects_returns_envelope_with_only_own_projects(
    client: AsyncClient, current_user: User, db_session: AsyncSession
) -> None:
    await ProjectFactory.create(user=current_user, name="Mine")
    other = await UserFactory.create()
    await ProjectFactory.create(user=other, name="Theirs")

    response = await client.get("/api/projects")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Mine"]
    assert body["limit"] == 50
    assert body["offset"] == 0


async def test_list_projects_honours_limit_and_offset(
    client: AsyncClient, current_user: User
) -> None:
    for i in range(3):
        await ProjectFactory.create(user=current_user, name=f"p{i}")

    response = await client.get("/api/projects", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


async def test_list_projects_invalid_limit_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/projects", params={"limit": 0})

    assert response.status_code == 422


async def test_get_project_returns_200_for_owner(
    client: AsyncClient, current_user: User
) -> None:
    project = await ProjectFactory.create(user=current_user, name="Owned")

    response = await client.get(f"/api/projects/{project.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Owned"


async def test_get_project_missing_returns_404_entity_not_found(
    client: AsyncClient,
) -> None:
    response = await client.get(f"/api/projects/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:learnflow:entity-not-found"


async def test_get_project_owned_by_other_user_returns_404(
    client: AsyncClient,
) -> None:
    other = await UserFactory.create()
    project = await ProjectFactory.create(user=other, name="NotYours")

    response = await client.get(f"/api/projects/{project.id}")

    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "Project not found"


async def test_get_project_invalid_uuid_returns_422(client: AsyncClient) -> None:
    response = await client.get("/api/projects/not-a-uuid")

    assert response.status_code == 422


async def test_update_project_returns_200_with_new_name(
    client: AsyncClient, current_user: User
) -> None:
    project = await ProjectFactory.create(user=current_user, name="Before")

    response = await client.put(f"/api/projects/{project.id}", json={"name": "After"})

    assert response.status_code == 200
    assert response.json()["name"] == "After"


async def test_update_project_owned_by_other_user_returns_404(
    client: AsyncClient,
) -> None:
    other = await UserFactory.create()
    project = await ProjectFactory.create(user=other)

    response = await client.put(f"/api/projects/{project.id}", json={"name": "Hijack"})

    assert response.status_code == 404


async def test_delete_project_returns_204_and_then_gone(
    client: AsyncClient, current_user: User
) -> None:
    project = await ProjectFactory.create(user=current_user)

    delete_response = await client.delete(f"/api/projects/{project.id}")
    get_response = await client.get(f"/api/projects/{project.id}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


async def test_delete_project_owned_by_other_user_returns_404(
    client: AsyncClient,
) -> None:
    other = await UserFactory.create()
    project = await ProjectFactory.create(user=other)

    response = await client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 404


async def test_delete_project_is_idempotent(
    client: AsyncClient, current_user: User
) -> None:
    project = await ProjectFactory.create(user=current_user)

    await client.delete(f"/api/projects/{project.id}")
    second = await client.delete(f"/api/projects/{project.id}")

    assert second.status_code == 204
