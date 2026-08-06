"""HTTP/SSE integration for the ``title_updated`` event.

Complements the sociable-unit relay tests (``test_auto_title_relay.py``) at the
one place they can't reach: the wire. The event is serialised by the generic
``_event_generator`` mapping, so what this pins is that a title really does
leave the server as ``data: {"type": "title_updated", "title": ...}`` inside the
same stream — the shape the frontend's ``SSEEvent`` union has to match.
"""

from __future__ import annotations

import pytest
from app.models.user import User
from httpx import AsyncClient
from learnflow_testing.factories import ProjectFactory
from learnflow_testing.sse import collect_sse

from tests.chat.conftest import (
    ThreadViewFactory,
    TitleWiring,
    security_block_event,
    text_chunk_event,
)

pytestmark = pytest.mark.integration


async def test_stream_delivers_generated_title_as_non_terminal_event(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_title_runner: TitleWiring,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    wired_title_runner.title_generator.title = "Квадратные уравнения"
    wired_title_runner.runner.last_ai_message_id = "m1"
    wired_title_runner.runner.events = [text_chunk_event("Привет")]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    payload = {"content": "Что такое дискриминант"}
    async with client.stream("POST", url, json=payload) as response:
        events = await collect_sse(response)

    types = [e.json()["type"] for e in events]
    assert types == ["text_chunk", "title_updated", "done"]
    assert events[1].json() == {
        "type": "title_updated",
        "title": "Квадратные уравнения",
    }


async def test_stream_omits_title_when_guard_blocks_the_first_event(
    client: AsyncClient,
    current_user: User,
    thread_factory: type[ThreadViewFactory],
    wired_title_runner: TitleWiring,
) -> None:
    project = await ProjectFactory.create(user=current_user)
    thread = await thread_factory.create(project=project)
    wired_title_runner.runner.events = [security_block_event()]

    url = f"/api/projects/{project.id}/chats/{thread.thread_id}/messages"
    async with client.stream("POST", url, json={"content": "prompt injection"}) as resp:
        events = await collect_sse(resp)

    # Blocked input never reaches the title model, so nothing is generated and
    # nothing is delivered — the stream is just the terminal block.
    assert [e.json()["type"] for e in events] == ["security_block"]
    assert wired_title_runner.title_generator.calls == []
