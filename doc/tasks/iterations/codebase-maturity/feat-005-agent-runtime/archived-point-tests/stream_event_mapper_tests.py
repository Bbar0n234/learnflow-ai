"""feat-005: StreamEventMapper — graph updates → SSE events (concern 4)."""

from app.agent.stream_events import StreamEventMapper
from langchain_core.messages import AIMessage, ToolMessage

_MAPPER = StreamEventMapper()


def test_agent_tool_calls_become_tool_start() -> None:
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_section", "args": {}, "id": "c1", "type": "tool_call"}
        ],
    )
    events = _MAPPER.updates({"agent": {"messages": [ai]}})
    assert [e.type for e in events] == ["tool_start"]
    assert events[0].data == {"tool": "get_section", "call_id": "c1"}


def test_tool_message_becomes_tool_end() -> None:
    tm = ToolMessage(content="ok", name="get_section", tool_call_id="c1")
    events = _MAPPER.updates({"tools": {"messages": [tm]}})
    assert [e.type for e in events] == ["tool_end"]
    assert events[0].data == {"tool": "get_section", "call_id": "c1"}


def test_create_artifact_emits_artifact_created() -> None:
    tm = ToolMessage(
        content="saved",
        name="create_artifact",
        tool_call_id="c2",
        artifact={"id": "a1", "title": "Plan", "type": "plan"},
    )
    events = _MAPPER.updates({"tools": {"messages": [tm]}})
    assert [e.type for e in events] == ["tool_end", "artifact_created"]
    artifact_event = events[1]
    assert artifact_event.data["id"] == "a1"
    assert artifact_event.data["title"] == "Plan"
    assert artifact_event.data["artifact_type"] == "plan"
    assert "type" not in artifact_event.data


def test_empty_updates_yield_nothing() -> None:
    assert _MAPPER.updates({}) == []
