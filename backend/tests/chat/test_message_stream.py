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
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory, UserFactory
from learnflow_testing.sse import collect_sse
from sqlalchemy.ext.asyncio import AsyncSession

from tests.chat.conftest import (
    FakeAgentRunner,
    error_event,
    security_block_event,
    text_chunk_event,
    trace_id_event,
)

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
        trace_id_event("tr-1"),
        text_chunk_event("Hello"),
        text_chunk_event(" world"),
    ]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    # trace_id is consumed by the service, never sent on the wire.
    assert types == ["text_chunk", "text_chunk", "done"]
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
        text_chunk_event("partial"),
        error_event("graph failed"),
    ]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    # token-before-error ordering and the prod ``detail`` payload (frontend reads
    # ``event.detail``) are both pinned; partial text survives the terminal.
    assert types == ["text_chunk", "error"]
    assert events[0].json()["content"] == "partial"
    assert events[-1].json()["detail"] == "graph failed"
    assert all(e.json()["type"] != "done" for e in events)


async def test_stream_security_block_is_terminal_without_done(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [
        text_chunk_event("partial answer"),
        security_block_event(),
    ]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    # security_block is a terminal event distinct from error: no trailing done,
    # the partial text emitted before the block is preserved on the wire, and
    # the payload is the generic prod shape — no reason/checkpoint/
    # detection_layer (design-brief § "Контракт SSE v2").
    assert types == ["text_chunk", "security_block"]
    assert events[0].json()["content"] == "partial answer"
    assert events[-1].json() == {"type": "security_block"}
    assert all(e.json()["type"] != "done" for e in events)


async def test_stream_runner_exception_yields_terminal_error_event(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [text_chunk_event("partial")]
    # Raise after the first event — models an in-graph crash not wrapped as an
    # error event; the API generator's try/except must emit a terminal error.
    wired_runner.raise_after = 1

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)

    last = events[-1].json()
    assert last["type"] == "error"
    # The terminal error payload uses ``detail`` per the SSE contract
    # (streaming.md, runner.py); the frontend reads ``event.detail``.
    assert last["detail"] == "Stream failed"


async def test_stream_accepts_empty_content(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [text_chunk_event("x")]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": ""}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)

    # Empty content is accepted at the API contract level (no min_length); the
    # stream runs and terminates normally. See runlog "Баги для Ф5".
    assert [e.json()["type"] for e in events] == ["text_chunk", "done"]


async def test_stream_hands_the_requested_attachments_to_the_runner(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The upload paths are the one part of the call the client controls beyond
    # the text, and the whole attachment feature hangs off them arriving: drop
    # them anywhere between the request body and ``AgentRunner.stream`` and the
    # turn still streams normally — the model simply never learns a file was
    # attached. Nothing downstream of the runner can notice, so the delivery is
    # pinned here, on the recorded call.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [text_chunk_event("ok")]
    attachments = ["uploads/lecture.md", "uploads/Лекция №1.md"]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream(
        "POST", url, json={"content": "разбери", "attachments": attachments}
    ) as response:
        assert response.status_code == 200
        await collect_sse(response)

    call = wired_runner.stream_calls[0]
    assert call.attachments == attachments
    assert (call.thread_id, call.content, call.project_id, call.user_id) == (
        thread.thread_id,
        "разбери",
        project.id,
        current_user.id,
    )


async def test_stream_without_attachments_passes_an_empty_list(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The counterpart of the case above: an ordinary message must not acquire
    # attachments out of nowhere, so the runner is told there are none.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.events = [text_chunk_event("ok")]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        await collect_sse(response)

    assert wired_runner.stream_calls[0].attachments == []


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
