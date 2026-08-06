"""HTTP integration for chat rename and delete.

Real repositories on the transactional ``db_session`` — the cascade of a chat
deletion is SQL (FK cascade, SET NULL) plus one hand-written cleanup of the
FK-less polymorphic disables, and none of that can be observed against fakes.
Only the agent runner is faked (``wired_runner``), which is also how the
best-effort checkpoint cleanup is made to fail on demand.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.artifact import Artifact
from app.models.mcp_server import MCPServerDisable, ThreadMCPServer
from app.models.thread_view import ThreadView
from app.models.user import User
from app.services.constants import DEFAULT_CHAT_TITLE, MAX_TITLE_LENGTH
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory, UserFactory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from tests.chat.conftest import FakeAgentRunner, ThreadViewFactory

pytestmark = pytest.mark.integration


async def _stored_title(session: AsyncSession, thread_id: uuid.UUID) -> str | None:
    """The title as it is in the DB — never the factory's local ORM object.

    A column-level SELECT bypasses the identity map, so a write that slipped
    past ownership or validation shows up here even though the test still holds
    the pre-request object.
    """
    result = await session.execute(
        select(ThreadView.title).where(ThreadView.thread_id == thread_id)
    )
    return result.scalar_one_or_none()


# --- rename ----------------------------------------------------------------


async def test_rename_chat_returns_200_and_persists_new_title(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}",
        json={"title": "Подготовка к ЕГЭ"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Подготовка к ЕГЭ"
    # Persisted, not just echoed back.
    reread = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")
    assert reread.json()["title"] == "Подготовка к ЕГЭ"


async def test_rename_chat_accepts_title_at_the_length_limit(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    title = "я" * MAX_TITLE_LENGTH

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}", json={"title": title}
    )

    assert response.status_code == 200
    assert response.json()["title"] == title


@pytest.mark.parametrize(
    "body",
    [
        {"title": ""},
        {"title": "я" * (MAX_TITLE_LENGTH + 1)},
        {},
        {"title": None},
    ],
    ids=["empty", "over_limit", "missing", "null"],
)
async def test_rename_chat_rejects_invalid_title_with_422(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
    body: dict[str, object],
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}", json=body
    )

    assert response.status_code == 422
    assert await _stored_title(db_session, thread.thread_id) == DEFAULT_CHAT_TITLE


async def test_rename_chat_is_allowed_on_a_security_blocked_chat(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project, security_blocked=True)

    response = await client.put(
        f"/api/projects/{project.id}/chats/{thread.thread_id}",
        json={"title": "Инцидент"},
    )

    # Blocking stops the conversation, not the ownership of the chat: renaming
    # a blocked chat stays available (design-brief § Заблокированные чаты).
    assert response.status_code == 200
    assert response.json()["title"] == "Инцидент"


async def test_rename_chat_of_another_user_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    other = await UserFactory.create()
    other_project = await ProjectFactory.create(user=other)
    other_thread = await thread_factory.create(project=other_project)

    response = await client.put(
        f"/api/projects/{other_project.id}/chats/{other_thread.thread_id}",
        json={"title": "Не моё"},
    )

    assert response.status_code == 404
    assert await _stored_title(db_session, other_thread.thread_id) == DEFAULT_CHAT_TITLE


async def test_rename_chat_through_a_foreign_project_path_returns_404(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    other_project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    response = await client.put(
        f"/api/projects/{other_project.id}/chats/{thread.thread_id}",
        json={"title": "Чужой путь"},
    )

    # The chat is the user's own, but it does not live in the project named in
    # the path — the pair must match.
    assert response.status_code == 404
    assert await _stored_title(db_session, thread.thread_id) == DEFAULT_CHAT_TITLE


async def test_rename_missing_chat_returns_404(
    client: AsyncClient, current_user: User, wired_runner: FakeAgentRunner
) -> None:
    project = await ProjectFactory.create(user=current_user)

    response = await client.put(
        f"/api/projects/{project.id}/chats/{uuid.uuid4()}", json={"title": "Нет такого"}
    )

    assert response.status_code == 404


# --- delete ----------------------------------------------------------------


async def _thread_exists(session: AsyncSession, thread_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(ThreadView.thread_id).where(ThreadView.thread_id == thread_id)
    )
    return result.first() is not None


async def test_delete_chat_returns_204_and_removes_the_chat(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}"
    )

    assert response.status_code == 204
    assert not await _thread_exists(db_session, thread.thread_id)
    follow_up = await client.get(f"/api/projects/{project.id}/chats/{thread.thread_id}")
    assert follow_up.status_code == 404


async def test_delete_chat_twice_returns_204_both_times(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    url = f"/api/projects/{project.id}/chats/{thread.thread_id}"

    first = await client.delete(url)
    second = await client.delete(url)

    # DELETE is idempotent (api.md): deleting an already-deleted chat is a
    # success, not a 404 — this is why ownership is resolved by hand here.
    assert (first.status_code, second.status_code) == (204, 204)


async def test_delete_chat_is_allowed_on_a_security_blocked_chat(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project, security_blocked=True)

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}"
    )

    assert response.status_code == 204
    assert not await _thread_exists(db_session, thread.thread_id)


async def test_delete_chat_of_another_user_returns_404_and_keeps_it(
    client: AsyncClient,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    other = await UserFactory.create()
    other_project = await ProjectFactory.create(user=other)
    other_thread = await thread_factory.create(project=other_project)

    response = await client.delete(
        f"/api/projects/{other_project.id}/chats/{other_thread.thread_id}"
    )

    assert response.status_code == 404
    assert await _thread_exists(db_session, other_thread.thread_id)


async def test_delete_chat_through_a_foreign_project_path_returns_404(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    other_project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    response = await client.delete(
        f"/api/projects/{other_project.id}/chats/{thread.thread_id}"
    )

    assert response.status_code == 404
    assert await _thread_exists(db_session, thread.thread_id)


async def test_delete_chat_requests_checkpoint_cleanup(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)

    await client.delete(f"/api/projects/{project.id}/chats/{thread.thread_id}")

    # LangGraph checkpoints live outside our schema and are only reachable
    # through the runner — the outbound call *is* the contract here.
    assert wired_runner.deleted_threads == [thread.thread_id]


async def test_delete_chat_survives_a_failing_checkpoint_cleanup(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    wired_runner.raise_on_delete_thread = True

    with capture_logs() as logs:
        response = await client.delete(
            f"/api/projects/{project.id}/chats/{thread.thread_id}"
        )

    # The DB transaction is the source of truth and is already committed: a dead
    # checkpointer leaves orphaned checkpoints, never a live chat with a wiped
    # history, and never a failed request.
    assert response.status_code == 204
    assert not await _thread_exists(db_session, thread.thread_id)
    # Silent success would hide the orphans: the failure is still recorded, as a
    # warning rather than as a raised error. (This assertion used to live in a
    # service-level unit test built with ``session=None``; the delete path now
    # requires a session outright, so the degradation is only expressible here.)
    warnings = [
        entry
        for entry in logs
        if entry["log_level"] == "warning"
        and entry["event"] == "checkpoint thread deletion failed"
    ]
    assert len(warnings) == 1


async def test_delete_chat_clears_its_mcp_disables_and_servers(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    survivor = await thread_factory.create(project=project)
    thread_server = ThreadMCPServer(
        thread_id=thread.thread_id, name="tools", transport="http", url="http://mcp"
    )
    db_session.add(thread_server)
    await db_session.flush()
    db_session.add_all(
        [
            # Disabled at thread scope...
            MCPServerDisable(
                scope_type="thread",
                scope_id=thread.thread_id,
                server_id=uuid.uuid4(),
            ),
            # ...and a project-scope row pointing at this chat's own server:
            # only reachable while the server row still exists, which is why the
            # cleanup has to run before the chat row is deleted.
            MCPServerDisable(
                scope_type="project",
                scope_id=project.id,
                server_id=thread_server.id,
            ),
            # Another chat's disable — must survive untouched.
            MCPServerDisable(
                scope_type="thread",
                scope_id=survivor.thread_id,
                server_id=uuid.uuid4(),
            ),
        ]
    )
    await db_session.flush()

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}"
    )

    assert response.status_code == 204
    remaining = (await db_session.execute(select(MCPServerDisable.scope_id))).scalars()
    assert list(remaining) == [survivor.thread_id]
    servers = await db_session.execute(
        select(ThreadMCPServer.id).where(ThreadMCPServer.thread_id == thread.thread_id)
    )
    assert servers.first() is None


async def test_delete_chat_keeps_its_artifacts_in_the_project(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    thread_factory: type[ThreadViewFactory],
    wired_runner: FakeAgentRunner,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    artifact = Artifact(
        project_id=project.id,
        thread_id=thread.thread_id,
        title="Конспект",
        type="markdown",
        content="# Конспект",
    )
    db_session.add(artifact)
    await db_session.flush()

    response = await client.delete(
        f"/api/projects/{project.id}/chats/{thread.thread_id}"
    )

    assert response.status_code == 204
    stored = await db_session.execute(
        select(Artifact.thread_id).where(Artifact.id == artifact.id)
    )
    # Artifacts outlive the chat they were produced in and stay in the project
    # (FK SET NULL) — deleting a chat is not deleting the user's work.
    assert stored.scalar_one() is None
