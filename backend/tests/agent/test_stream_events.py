"""Unit: graph payload -> wire shape, for both roads a tool call takes.

Two translations live in ``stream_events`` and both are pure functions of a
payload, so both are exercised here:

* ``StreamEventMapper`` over a dict shaped like LangGraph's
  ``stream_mode="updates"`` output — today that channel carries exactly one
  event of its own (``tool_call_cancelled``) plus the ledger that decides when
  it fires;
* ``tool_result_envelope``/``artifact_envelopes`` over a single ``ToolMessage``
  — the ``custom``-channel envelopes the tools node writes itself, per
  finished call, including the artifact ``type``->``artifact_type`` remap.
  ``artifact_envelopes`` reads ``ToolMessage.artifact`` as a *list* (one
  element per file the call touched) and turns each element into its own
  ``artifact_created``/``artifact_updated`` envelope, keyed by that element's
  ``kind``.

Which of the two carries ``tool_result`` is not cosmetic: a node update
reaches the runner only when the *whole* batch is done, so a mapper-emitted
result would make every call of a turn wait for the slowest one. The cases
below pin the split — the mapper stays silent on a tools payload, the envelope
builders own the shape.
"""

from __future__ import annotations

import pytest
from app.agent.stream_events import (
    StreamEventMapper,
    artifact_envelopes,
    make_tool_result_reporter,
    tool_result_envelope,
)
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
def test_a_tools_payload_emits_nothing_on_the_updates_channel(
    mapper: StreamEventMapper,
) -> None:
    # The node has already reported this result on the custom channel, the
    # moment its own call finished. A second emission here would double every
    # ``tool_result`` on the wire; worse, an emission *only* here would put the
    # whole turn back on batch time — which is the regression this case exists
    # to catch, since nothing else about the payload would look wrong.
    data = {
        "tools": {
            "messages": [
                ToolMessage(content="result", tool_call_id="c1", name="search")
            ]
        }
    }

    assert mapper.updates(data) == []


@pytest.mark.unit
def test_a_tool_message_becomes_a_tool_result_envelope() -> None:
    message = ToolMessage(content="result", tool_call_id="c1", name="search")

    assert tool_result_envelope(message) == {
        "type": "tool_result",
        "data": {
            "call_id": "c1",
            "tool": "search",
            "status": "success",
            "content": "result",
            "truncated": False,
        },
    }


@pytest.mark.unit
def test_a_nested_call_is_attributed_to_its_parent() -> None:
    # The subagent's own tool calls ride the same envelope; the only difference
    # is the attribution the feed nests them by.
    message = ToolMessage(content="result", tool_call_id="c1", name="search")

    envelope = tool_result_envelope(message, parent_call_id="outer-1")

    assert envelope["data"]["parent_call_id"] == "outer-1"


@pytest.mark.unit
def test_create_artifact_yields_an_artifact_envelope_with_remapped_type() -> None:
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="create_artifact",
        artifact=[{"type": "note", "id": "a1", "title": "T", "kind": "created"}],
    )

    envelopes = artifact_envelopes(message)

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope["type"] == "artifact_created"
    assert envelope["data"]["artifact_type"] == "note"
    assert "type" not in envelope["data"]
    assert "kind" not in envelope["data"]
    assert envelope["data"]["id"] == "a1"


@pytest.mark.unit
def test_create_artifact_without_artifact_payload_yields_no_artifact_envelope() -> None:
    message = ToolMessage(content="ok", tool_call_id="c1", name="create_artifact")

    assert artifact_envelopes(message) == []


@pytest.mark.unit
def test_an_updated_element_yields_an_artifact_updated_envelope_with_its_diff() -> None:
    # A job/write_file overwrite reports kind="updated" with a line-count diff
    # (design-brief § «Артефакты»); the event type carries the distinction, so
    # kind itself is dropped from the payload rather than forwarded raw.
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="write_file",
        artifact=[
            {
                "type": "md",
                "id": "a1",
                "title": "notes.md",
                "kind": "updated",
                "diff": {"added": 3, "removed": 1},
            }
        ],
    )

    envelopes = artifact_envelopes(message)

    assert len(envelopes) == 1
    assert envelopes[0]["type"] == "artifact_updated"
    assert envelopes[0]["data"] == {
        "id": "a1",
        "title": "notes.md",
        "artifact_type": "md",
        "diff": {"added": 3, "removed": 1},
    }


@pytest.mark.unit
def test_multiple_elements_yield_one_envelope_each_in_order() -> None:
    # A job touching several files -> N envelopes off one ToolMessage
    # (design-brief: "джоба с N файлами -> N ArtifactPart").
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="execute_code",
        artifact=[
            {"type": "png", "id": "a1", "title": "plot.png", "kind": "created"},
            {
                "type": "csv",
                "id": "a2",
                "title": "data.csv",
                "kind": "updated",
                "diff": {"added": 2, "removed": 0},
            },
        ],
    )

    envelopes = artifact_envelopes(message)

    assert [e["type"] for e in envelopes] == ["artifact_created", "artifact_updated"]
    assert [e["data"]["id"] for e in envelopes] == ["a1", "a2"]


@pytest.mark.unit
def test_unknown_node_and_non_message_payloads_emit_nothing(
    mapper: StreamEventMapper,
) -> None:
    assert mapper.updates({"other": {"messages": [HumanMessage(content="x")]}}) == []
    assert mapper.updates({}) == []


# --- tool_result: status and truncation --------------------------------------


@pytest.mark.unit
def test_failed_tool_execution_is_reported_as_status_error() -> None:
    # The feed has to tell a failed action from a successful one; the status
    # comes straight from the ``ToolMessage`` (set either by the tool itself or
    # by ``ToolNode``'s error handling).
    message = ToolMessage(
        content="boom: connection refused",
        tool_call_id="c1",
        name="search",
        status="error",
    )

    data = tool_result_envelope(message)["data"]

    assert data["status"] == "error"
    assert data["content"] == "boom: connection refused"


@pytest.mark.unit
def test_oversized_tool_result_is_truncated_and_flagged() -> None:
    message = ToolMessage(
        content="y" * (TRUNCATION_LIMIT * 3),
        tool_call_id="c1",
        name="firecrawl_scrape",
    )

    data = tool_result_envelope(message)["data"]

    assert len(data["content"]) == TRUNCATION_LIMIT
    assert data["truncated"] is True


# --- artifact_created: by attribute, not by tool name ------------------------


@pytest.mark.unit
def test_any_tool_returning_an_artifact_gets_an_artifact_envelope() -> None:
    # The event follows ``response_format="content_and_artifact"``, so a tool
    # outside the former hardcoded whitelist gets it too — that is the whole
    # point of the by-attribute rule (streaming.md § «tool_result /
    # artifact_created»).
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="some_future_tool",
        artifact=[{"type": "image", "id": "a9", "title": "Diagram", "kind": "created"}],
    )

    envelopes = artifact_envelopes(message)

    assert len(envelopes) == 1
    assert envelopes[0]["type"] == "artifact_created"
    assert envelopes[0]["data"] == {
        "artifact_type": "image",
        "id": "a9",
        "title": "Diagram",
    }


@pytest.mark.unit
def test_a_reporter_puts_the_result_before_its_artifact() -> None:
    # Order is contract: the feed attaches the artifact to the row the result
    # just closed, so one writer emits both, result first.
    written: list[dict[str, object]] = []
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="create_artifact",
        artifact=[{"type": "note", "id": "a1", "title": "T", "kind": "created"}],
    )

    make_tool_result_reporter(written.append)(message)

    assert [item["type"] for item in written] == ["tool_result", "artifact_created"]


@pytest.mark.unit
def test_a_reporter_emits_one_envelope_per_artifact_element() -> None:
    # A job that touched two files reports its result once, then two artifact
    # envelopes — the reporter, not the caller, fans the list out.
    written: list[dict[str, object]] = []
    message = ToolMessage(
        content="ok",
        tool_call_id="c1",
        name="execute_code",
        artifact=[
            {"type": "png", "id": "a1", "title": "plot.png", "kind": "created"},
            {"type": "csv", "id": "a2", "title": "data.csv", "kind": "created"},
        ],
    )

    make_tool_result_reporter(written.append)(message)

    assert [item["type"] for item in written] == [
        "tool_result",
        "artifact_created",
        "artifact_created",
    ]


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
    # ``guard_tool_result`` stamps the same ``security_redacted`` flag on a
    # ``ToolMessage`` for an unrelated TOOL_RESULT redaction: the call did run,
    # so it resolves as a result (reported by the node itself), never as a
    # cancellation. Reading that flag as a cut would end the turn's rows with a
    # cancellation the user's screen already contradicts.
    mapper.note_call_announced("c1")
    mapper.updates(
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

    assert mapper.updates(_guard_cut_turn()) == []
