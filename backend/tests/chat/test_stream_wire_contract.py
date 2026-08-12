"""HTTP integration: how a v2 event turns into an SSE frame, end to end.

``test_message_stream.py`` covers the transport basics (ordering, terminals,
headers, the 403/404 gates); this suite covers what the transport *does to* a
v2 event: the route -> ``ChatService`` -> ``_event_generator`` ->
``StreamingResponse`` chain is real, and the assertions are on the serialised
frame — ``data: {...}\\n\\n`` with ``type`` merged into the event's own payload,
nothing dropped, renamed or nested along the way. That flattening is the step
where a field can quietly disappear between the runner and the browser, and the
nesting/terminal/forward-compat semantics below are the transport's own
behaviour, not the mappers'.

**What this suite is not**: the oracle for the payloads themselves. The runner
is faked here, so the events come from the builders in ``tests/chat/conftest.py``
which mirror prod by hand. That a real run produces exactly these fields is
proven where the events are born — the mapper units (``test_stream_events.py``,
``test_token_chunk_mapper.py``) and the real-``astream`` runs in
``tests/agent/test_runner.py`` — while the *set* of types the builders may use
is tied to prod by the AST vocabulary guard in ``test_chat_service.py``. Read
those three together for the full contract; this file guarantees that whatever
the runner emits reaches the client unmangled.
"""

from __future__ import annotations

import pytest
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.models.user import User
from app.repositories.thread_view import ThreadViewRepository
from app.services.agent_runner import StreamEvent
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory
from learnflow_testing.sse import collect_sse
from sqlalchemy.ext.asyncio import AsyncSession

from tests.chat.conftest import (
    FakeAgentRunner,
    agent_event_event,
    artifact_created_event,
    artifact_updated_event,
    cancelled_event,
    heartbeat_event,
    reasoning_chunk_event,
    stream_started_event,
    text_chunk_event,
    tool_call_args_event,
    tool_call_cancelled_event,
    tool_call_started_event,
    tool_result_event,
)

pytestmark = pytest.mark.integration


async def _make_thread(
    db_session: AsyncSession, user: User
) -> tuple[Project, ThreadView]:
    project = await ProjectFactory.create(user=user)
    thread = await ThreadViewRepository(db_session).create(
        project_id=project.id, title="Chat"
    )
    return project, thread


async def _run(
    client: AsyncClient, project: Project, thread: ThreadView
) -> list[dict[str, object]]:
    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "hi"}) as response:
        assert response.status_code == 200
        events = await collect_sse(response)
    return [event.json() for event in events]


async def test_a_full_v2_turn_reaches_the_wire_with_documented_payloads(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [
        stream_started_event(),
        heartbeat_event(),
        reasoning_chunk_event("let me search"),
        tool_call_started_event("c1", "firecrawl_search"),
        tool_call_args_event("c1", '{"query": "cats"}'),
        tool_result_event("c1", "firecrawl_search", content="10 hits"),
        agent_event_event("sphere_write", {"section_id": "s1"}),
        text_chunk_event("Here you go"),
    ]

    payloads = await _run(client, project, thread)

    assert payloads == [
        {"type": "stream_started"},
        {"type": "heartbeat"},
        {"type": "reasoning_chunk", "content": "let me search"},
        {"type": "tool_call_started", "call_id": "c1", "tool": "firecrawl_search"},
        {
            "type": "tool_call_args",
            "call_id": "c1",
            "args": '{"query": "cats"}',
            "truncated": False,
        },
        {
            "type": "tool_result",
            "call_id": "c1",
            "tool": "firecrawl_search",
            "status": "success",
            "content": "10 hits",
            "truncated": False,
        },
        {
            "type": "agent_event",
            "kind": "sphere_write",
            "payload": {"section_id": "s1"},
        },
        {"type": "text_chunk", "content": "Here you go"},
        # No trace_id was emitted by the runner, so the terminal carries an
        # empty one rather than dropping the field.
        {"type": "done", "message_id": "m1", "trace_id": ""},
    ]


async def test_nested_subagent_steps_carry_parent_call_id_on_the_wire(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # A subagent's step is the same event type as the main agent's, told apart
    # only by ``parent_call_id`` — which is what lets the feed nest it under the
    # ``run_subagent`` row instead of showing it as a sibling.
    project, thread = await _make_thread(db_session, current_user)
    nested_started = StreamEvent(
        type="tool_call_started",
        data={"call_id": "i1", "tool": "firecrawl_search", "parent_call_id": "c1"},
    )
    wired_runner.events = [
        tool_call_started_event("c1", "run_subagent"),
        nested_started,
        agent_event_event("memory_write", {"key": "ru"}, parent_call_id="c1"),
    ]

    payloads = await _run(client, project, thread)

    assert payloads[1] == {
        "type": "tool_call_started",
        "call_id": "i1",
        "tool": "firecrawl_search",
        "parent_call_id": "c1",
    }
    assert payloads[2]["parent_call_id"] == "c1"
    # The outer call has no parent — nesting is opt-in per event.
    assert "parent_call_id" not in payloads[0]


async def test_a_cut_tool_call_is_reported_and_the_turn_still_completes(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # A call cut by the guard is not a terminal failure: the row is closed with
    # ``tool_call_cancelled`` and the turn goes on to its ``done``.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [
        tool_call_started_event("c1", "update_section"),
        tool_call_cancelled_event("c1"),
        text_chunk_event("I stopped that call"),
    ]

    payloads = await _run(client, project, thread)

    assert [p["type"] for p in payloads] == [
        "tool_call_started",
        "tool_call_cancelled",
        "text_chunk",
        "done",
    ]
    assert payloads[1] == {"type": "tool_call_cancelled", "call_id": "c1"}


async def test_cancelled_is_terminal_without_done(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # User cancellation is its own terminal event now, not an ``error`` with a
    # message the frontend had to string-match to suppress its error toast.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [text_chunk_event("half an answ"), cancelled_event()]

    payloads = await _run(client, project, thread)

    assert [p["type"] for p in payloads] == ["text_chunk", "cancelled"]
    assert payloads[-1] == {"type": "cancelled"}


async def test_an_event_type_the_transport_has_never_heard_of_still_ships(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # Forward-compat (streaming.md § Forward-compat): the contract grows by
    # adding event types, so the transport must stay a passthrough rather than
    # a whitelist — a future ``title_updated`` has to reach the client without
    # touching this layer.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [
        StreamEvent(type="title_updated", data={"title": "New title"}),
        text_chunk_event("ok"),
    ]

    payloads = await _run(client, project, thread)

    assert payloads[0] == {"type": "title_updated", "title": "New title"}


async def test_artifact_events_keep_both_their_event_type_and_the_files_type(
    client: AsyncClient,
    current_user: User,
    db_session: AsyncSession,
    wired_runner: FakeAgentRunner,
) -> None:
    # The frame is flat (`{"type": event.type, **event.data}`), so a payload
    # key literally named `type` would overwrite the event's own — which is
    # why the file's type travels as `artifact_type`. The update also has to
    # arrive with its line counters intact: that is what the "обновлён · +N −M"
    # badge is drawn from.
    project, thread = await _make_thread(db_session, current_user)
    wired_runner.last_ai_message_id = "m1"
    wired_runner.events = [
        artifact_created_event("chart.png"),
        artifact_updated_event("lecture-1/slides.md"),
    ]

    payloads = await _run(client, project, thread)

    assert payloads[:2] == [
        {
            "type": "artifact_created",
            "path": "chart.png",
            "title": "chart.png",
            "artifact_type": "png",
        },
        {
            "type": "artifact_updated",
            "path": "lecture-1/slides.md",
            "title": "slides.md",
            "artifact_type": "md",
            "diff": {"added": 1, "removed": 1},
        },
    ]
