"""Canary: HTTP handler through the authenticated ASGI client.

Proves route -> service -> repository -> real Postgres runs behind the
auth-override fixture (no real JWT). Not coverage; a smoke of the seam.
"""

from __future__ import annotations

import pytest
from app.models.user import User
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.integration
async def test_list_projects_returns_authenticated_users_project(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await ProjectFactory.create(user=current_user, name="Visible project")

    response = await client.get("/api/projects")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Visible project"]
