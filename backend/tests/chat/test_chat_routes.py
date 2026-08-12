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
from app.services.agent_runner import (
    ArtifactPart,
    AttachmentRef,
    Message,
    ReasoningPart,
    TextPart,
    ToolCallPart,
)
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


async def test_get_chat_returns_typed_parts_of_the_assistant_turn(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The persisted trace of the turn (design-brief § «Модель typed parts»):
    # history has to render as the same activity feed the live stream drew, so
    # the API ships the ordered parts alongside the flat ``content`` kept for
    # backwards compatibility. This is T2's read contract — every field of the
    # ``tool_call`` part is what a feed row is built from.
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    wired_runner.history = [
        Message(
            id="m1",
            role="assistant",
            content="found it",
            parts=[
                ReasoningPart(content="I should search"),
                ToolCallPart(
                    call_id="c1",
                    tool="firecrawl_search",
                    args='{"query": "cats"}',
                    args_truncated=False,
                    status="success",
                    result_preview="10 hits",
                    result_truncated=False,
                ),
                TextPart(content="found it"),
            ],
        )
    ]

    response = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    assert response.status_code == 200
    message = response.json()["messages"][0]
    assert message["content"] == "found it"
    assert message["parts"] == [
        {"type": "reasoning", "content": "I should search"},
        {
            "type": "tool_call",
            "call_id": "c1",
            "tool": "firecrawl_search",
            "args": '{"query": "cats"}',
            "args_truncated": False,
            "status": "success",
            "result_preview": "10 hits",
            "result_truncated": False,
        },
        {"type": "text", "content": "found it"},
    ]


async def test_get_chat_returns_empty_parts_for_a_plain_message(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # ``parts`` is an addition, not a replacement: a message without them (a
    # user turn, a degraded read) still serialises, with an empty list.
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    wired_runner.history = [Message(id="u1", role="user", content="question")]

    response = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    assert response.json()["messages"][0]["parts"] == []


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


async def test_get_chat_ships_an_artifact_part_with_its_wire_field_names(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The chat <-> artifact link is a typed part now, not a PG join (ADR-032):
    # this is what the feed rebuilds a card from after a reload. The file's own
    # type ships as ``artifact_type`` — ``type`` is taken by the part
    # discriminator, and colliding on it is exactly how a card would lose its
    # kind on the wire.
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    wired_runner.history = [
        Message(
            id="m1",
            role="assistant",
            content="updated",
            parts=[
                ArtifactPart(
                    path="lecture-1/slides.md",
                    title="slides.md",
                    type="md",
                    kind="updated",
                    diff={"added": 3, "removed": 1},
                )
            ],
        )
    ]

    response = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    assert response.json()["messages"][0]["parts"] == [
        {
            "type": "artifact",
            "path": "lecture-1/slides.md",
            "title": "slides.md",
            "artifact_type": "md",
            "kind": "updated",
            "diff": {"added": 3, "removed": 1},
        }
    ]


async def test_get_chat_ships_the_attachments_of_a_user_message(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The chip after a page reload comes from here, not from parsing the note
    # out of the message text (the note never reaches the UI at all).
    project = await ProjectFactory.create(user=current_user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    wired_runner.history = [
        Message(
            id="u1",
            role="user",
            content="summarize this",
            attachments=[
                AttachmentRef(path="uploads/lecture.pdf", title="lecture.pdf")
            ],
        )
    ]

    response = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    message = response.json()["messages"][0]
    assert message["content"] == "summarize this"
    assert message["attachments"] == [
        {"path": "uploads/lecture.pdf", "title": "lecture.pdf"}
    ]
