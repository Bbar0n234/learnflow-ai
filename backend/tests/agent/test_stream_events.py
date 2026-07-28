"""Unit: ``StreamEventMapper`` — graph ``updates`` payload -> domain StreamEvents.

Pure translation over a dict shaped like LangGraph's ``stream_mode="updates"``
output. We feed representative node payloads and assert the emitted SSE-facing
events (type + data), including the artifact ``type``->``artifact_type`` remap.
"""

from __future__ import annotations

import pytest
from app.agent.stream_events import StreamEventMapper
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


@pytest.fixture
def mapper() -> StreamEventMapper:
    return StreamEventMapper()


@pytest.mark.unit
def test_agent_tool_calls_emit_nothing(mapper: StreamEventMapper) -> None:
    # Tool-call announcement moved to the token channel (T1.3's early
    # ``tool_call_started`` from ``tool_call_chunks``); the updates channel no
    # longer duplicates it via the removed ``tool_start``.
    data = {
        "agent": {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "search", "args": {}, "id": "c1"},
                        {"name": "lookup", "args": {}, "id": "c2"},
                    ],
                )
            ]
        }
    }

    assert mapper.updates(data) == []


@pytest.mark.unit
def test_agent_message_without_tool_calls_emits_nothing(
    mapper: StreamEventMapper,
) -> None:
    data = {"agent": {"messages": [AIMessage(content="plain answer")]}}

    assert mapper.updates(data) == []


@pytest.mark.unit
def test_tool_message_emits_tool_result_event(mapper: StreamEventMapper) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(content="result", tool_call_id="c1", name="search")
            ]
        }
    }

    events = mapper.updates(data)

    assert [(e.type, e.data) for e in events] == [
        (
            "tool_result",
            {
                "call_id": "c1",
                "tool": "search",
                "status": "success",
                "content": "result",
                "truncated": False,
            },
        )
    ]


@pytest.mark.unit
def test_create_artifact_emits_artifact_created_with_remapped_type(
    mapper: StreamEventMapper,
) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(
                    content="ok",
                    tool_call_id="c1",
                    name="create_artifact",
                    artifact={"type": "note", "id": "a1", "title": "T"},
                )
            ]
        }
    }

    events = mapper.updates(data)

    types = [e.type for e in events]
    assert types == ["tool_result", "artifact_created"]
    artifact_event = events[1]
    assert artifact_event.data["artifact_type"] == "note"
    assert "type" not in artifact_event.data
    assert artifact_event.data["id"] == "a1"


@pytest.mark.unit
def test_create_artifact_without_artifact_payload_only_emits_tool_result(
    mapper: StreamEventMapper,
) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(content="ok", tool_call_id="c1", name="create_artifact")
            ]
        }
    }

    events = mapper.updates(data)

    assert [e.type for e in events] == ["tool_result"]


@pytest.mark.unit
def test_unknown_node_and_non_message_payloads_emit_nothing(
    mapper: StreamEventMapper,
) -> None:
    assert mapper.updates({"other": {"messages": [HumanMessage(content="x")]}}) == []
    assert mapper.updates({}) == []
