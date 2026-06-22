"""HTTP integration for the SSE message endpoint — the critical streaming path.

Drives the real route through the async ``client.stream()`` so the full chain is
under test: ``ChatService.send_message`` -> ``_event_generator`` wire mapping ->
``StreamingResponse``. Only the agent runner is faked (``wired_runner``), so the
events flowing out are deterministic and we can assert their wire shape, order,
and terminal semantics.

The single-session footgun (parent conftest ``app`` docstring) is respected: each
stream is drained fully before any further request; no concurrent calls.
"""

from __future__ import annotations

import pytest
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import StreamEvent
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory, UserFactory
from learnflow_testing.sse import collect_sse
from sqlalchemy.ext.asyncio import AsyncSession

from tests.chat.conftest import FakeAgentRunner

pytestmark = pytest.mark.integration


async def _make_thread(
    db_session: AsyncSession, user: User, *, blocked: bool = False
) -> tuple[Project, ThreadView]:
    project = await ProjectFactory.create(user=user)
    repo = ThreadViewRepository(db_session)
    thread = await repo.create(project_id=project.id, title="Chat")
    if blocked:
        await repo.mark_security_blocked(thread.thread_id)
    return project, thread


async def test_stream_maps_events_in_order_and_terminates_with_done(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [
        StreamEvent(type="trace_id", data={"trace_id": "tr-1"}),
        StreamEvent(type="token", data={"content": "Hello"}),
        StreamEvent(type="token", data={"content": " world"}),
    ]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    # trace_id is consumed by the service, never sent on the wire.
    assert types == ["token", "token", "done"]
    assert events[0].json()["content"] == "Hello"
    done = events[-1].json()
    assert done == {"type": "done", "message_id": "m1", "trace_id": "tr-1"}


async def test_stream_error_event_is_terminal_without_done(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [
        StreamEvent(type="token", data={"content": "partial"}),
        StreamEvent(type="error", data={"message": "graph failed"}),
    ]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    assert types == ["token", "error"]
    assert all(e.json()["type"] != "done" for e in events)


async def test_stream_runner_exception_yields_terminal_error_event(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [StreamEvent(type="token", data={"content": "partial"})]
    # Raise after the first event — models an in-graph crash not wrapped as an
    # error event; the API generator's try/except must emit a terminal error.
    wired_runner.raise_after = 1

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)

    last = events[-1].json()
    assert last["type"] == "error"
    assert last["message"] == "Stream failed"


async def test_stream_accepts_empty_content(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [StreamEvent(type="token", data={"content": "x"})]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": ""}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)

    # Empty content is accepted at the API contract level (no min_length); the
    # stream runs and terminates normally. See runlog "Баги для Ф5".
    assert [e.json()["type"] for e in events] == ["token", "done"]


async def test_send_message_to_blocked_thread_returns_403(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user, blocked=True)

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    response = await client.post(url, json={"content": "hi"})

    assert response.status_code == 403


async def test_send_message_across_users_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    other = await UserFactory.create()
    project, thread = await _make_thread(db_session, other)

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    response = await client.post(url, json={"content": "hi"})

    assert response.status_code == 404


@pytest.mark.parametrize("expected", [True, False])
async def test_cancel_returns_runner_result(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
    expected: bool,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.cancel_result = expected

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/cancel"
    response = await client.post(url)

    assert response.status_code == 200
    assert response.json() == {"ok": expected}
