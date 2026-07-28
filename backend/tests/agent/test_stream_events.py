"""Unit: ``StreamEventMapper`` — graph ``updates`` payload -> domain StreamEvents.

Pure translation over a dict shaped like LangGraph's ``stream_mode="updates"``
output. We feed representative node payloads and assert the emitted SSE-facing
events (type + data), including the artifact ``type``->``artifact_type`` remap.
"""

from __future__ import annotations

import pytest
from app.agent.stream_events import StreamEventMapper
from app.agent.text_limits import TRUNCATION_LIMIT
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


# --- tool_result: status and truncation --------------------------------------


@pytest.mark.unit
def test_failed_tool_execution_is_reported_as_status_error(
    mapper: StreamEventMapper,
) -> None:
    # The feed has to tell a failed action from a successful one; the status
    # comes straight from the ``ToolMessage`` (set either by the tool itself or
    # by ``ToolNode``'s error handling).
    data = {
        "tools": {
            "messages": [
                ToolMessage(
                    content="boom: connection refused",
                    tool_call_id="c1",
                    name="search",
                    status="error",
                )
            ]
        }
    }

    events = mapper.updates(data)

    assert [e.data["status"] for e in events] == ["error"]
    assert events[0].data["content"] == "boom: connection refused"


@pytest.mark.unit
def test_oversized_tool_result_is_truncated_and_flagged(
    mapper: StreamEventMapper,
) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(
                    content="y" * (TRUNCATION_LIMIT * 3),
                    tool_call_id="c1",
                    name="firecrawl_scrape",
                )
            ]
        }
    }

    events = mapper.updates(data)

    assert len(events[0].data["content"]) == TRUNCATION_LIMIT
    assert events[0].data["truncated"] is True


# --- artifact_created: by attribute, not by tool name ------------------------


@pytest.mark.unit
def test_any_tool_returning_an_artifact_emits_artifact_created(
    mapper: StreamEventMapper,
) -> None:
    # The event follows ``response_format="content_and_artifact"``, so a tool
    # outside the former hardcoded whitelist gets it too — that is the whole
    # point of the by-attribute rule (streaming.md § «tool_result /
    # artifact_created»).
    data = {
        "tools": {
            "messages": [
                ToolMessage(
                    content="ok",
                    tool_call_id="c1",
                    name="some_future_tool",
                    artifact={"type": "image", "id": "a9", "title": "Diagram"},
                )
            ]
        }
    }

    events = mapper.updates(data)

    assert [e.type for e in events] == ["tool_result", "artifact_created"]
    assert events[1].data == {
        "artifact_type": "image",
        "id": "a9",
        "title": "Diagram",
    }


# --- tool_call_cancelled: a guard cut a generated call -----------------------


def _guard_cut_turn() -> dict[str, object]:
    """Agent-node payload after ``guard_tool_call_args`` stripped the calls."""
    return {
        "agent": {
            "messages": [
                AIMessage(
                    content="",
                    additional_kwargs={"security_redacted": True},
                )
            ]
        }
    }


@pytest.mark.unit
def test_calls_cut_by_the_guard_are_cancelled_in_announcement_order(
    mapper: StreamEventMapper,
) -> None:
    # By the time the redacted message arrives its ``tool_calls`` are empty, so
    # the only record of what was announced live is the mapper's own
    # bookkeeping — without it the feed would keep two rows spinning forever.
    mapper.note_call_announced("c1")
    mapper.note_call_announced("c2")

    events = mapper.updates(_guard_cut_turn())

    assert [(e.type, e.data) for e in events] == [
        ("tool_call_cancelled", {"call_id": "c1"}),
        ("tool_call_cancelled", {"call_id": "c2"}),
    ]


@pytest.mark.unit
def test_a_call_that_already_produced_a_result_is_not_cancelled(
    mapper: StreamEventMapper,
) -> None:
    mapper.note_call_announced("c1")
    mapper.note_call_announced("c2")
    mapper.updates(
        {"tools": {"messages": [ToolMessage(content="ok", tool_call_id="c1")]}}
    )

    events = mapper.updates(_guard_cut_turn())

    assert [e.data["call_id"] for e in events] == ["c2"]


@pytest.mark.unit
def test_cut_calls_are_cancelled_only_once(mapper: StreamEventMapper) -> None:
    mapper.note_call_announced("c1")
    mapper.updates(_guard_cut_turn())

    assert mapper.updates(_guard_cut_turn()) == []


@pytest.mark.unit
def test_a_plain_answer_does_not_cancel_an_announced_call(
    mapper: StreamEventMapper,
) -> None:
    # A turn that simply ends with text (no redaction) must not be mistaken for
    # a guard cut, or every ordinary run would emit spurious cancellations.
    mapper.note_call_announced("c1")

    events = mapper.updates(
        {"agent": {"messages": [AIMessage(content="here is the answer")]}}
    )

    assert events == []


@pytest.mark.unit
def test_a_redacted_tool_result_does_not_cancel_an_announced_call(
    mapper: StreamEventMapper,
) -> None:
    # ``guard_tool_results`` stamps the same ``security_redacted`` flag on a
    # ``ToolMessage`` for an unrelated TOOL_RESULT redaction: the call did run,
    # so it resolves as a result, never as a cancellation.
    mapper.note_call_announced("c1")

    events = mapper.updates(
        {
            "tools": {
                "messages": [
                    ToolMessage(
                        content="[blocked]",
                        tool_call_id="c1",
                        name="search",
                        additional_kwargs={"security_redacted": True},
                    )
                ]
            }
        }
    )

    assert [e.type for e in events] == ["tool_result"]
