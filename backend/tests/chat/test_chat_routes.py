"""HTTP integration for chat CRUD routes.

Real repositories on the transactional ``db_session`` (so the route's SQL —
pagination, ownership filter, eager project load — is exercised); only the agent
runner is faked via ``wired_runner``. Ownership is enforced by the dependency
chain (``get_user_project`` / ``get_user_thread``) returning 404 across users.
"""

from __future__ import annotations

import pytest
from app.models.user import User
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import Message
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy.ext.asyncio import AsyncSession

from tests.chat.conftest import FakeAgentRunner

pytestmark = pytest.mark.integration


async def test_create_chat_ignores_request_body(
    client: AsyncClient, current_user: User, wired_runner: FakeAgentRunner
) -> None:
    project = await ProjectFactory.create(user=current_user)

    # Foreign body is ignored: the endpoint takes no request body anymore
    # (ChatCreate removed) — the server always assigns the placeholder title.
    response = await client.post(
        f"/api/projects/{project.id}/chats", json={"title": "My chat"}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Новый чат"
    assert body["thread_id"]


async def test_create_chat_defaults_title_when_omitted(
    client: AsyncClient, current_user: User, wired_runner: FakeAgentRunner
) -> None:
    project = await ProjectFactory.create(user=current_user)

    response = await client.post(f"/api/projects/{project.id}/chats")

    assert response.status_code == 201
    assert response.json()["title"] == "Новый чат"


async def test_create_chat_in_other_users_project_returns_404(
    client: AsyncClient, wired_runner: FakeAgentRunner
) -> None:
    other = await UserFactory.create()
    other_project = await ProjectFactory.create(user=other)

    response = await client.post(f"/api/projects/{other_project.id}/chats")

    assert response.status_code == 404


async def test_list_chats_paginates(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    repo = ThreadViewRepository(db_session)
    for i in range(3):
        await repo.create(project_id=project.id, title=f"chat-{i}")

    response = await client.get(
        f"/api/projects/{project.id}/chats", params={"limit": 2, "offset": 0}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


async def test_get_chat_returns_message_history(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    wired_runner.history = [Message(id="m1", role="assistant", content="hi there")]

    response = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Chat"
    assert [m["content"] for m in body["messages"]] == ["hi there"]


async def test_get_chat_across_users_returns_404(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    other = await UserFactory.create()
    other_project = await ProjectFactory.create(user=other)
    other_thread = await ThreadViewRepository(db_session).create(
        project_id=other_project.id, title="Secret"
    )

    response = await client.get(
        f"/api/projects/{other_project.id}/chats/{other_thread.thread_id}"
    )

    assert response.status_code == 404


async def test_recent_chats_lists_users_threads_with_project_name(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user, name="Algebra")
    await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Recent chat"
    )

    response = await client.get("/api/chats/recent")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    titles = {item["title"]: item["project_name"] for item in body["items"]}
    assert titles.get("Recent chat") == "Algebra"
