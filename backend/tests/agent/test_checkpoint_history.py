"""Unit: ``CheckpointHistory`` — read-side adapter over the checkpointer.

The only collaborator is the checkpointer; it is болезненная граница (real one is
Postgres/in-memory infra), so it is stubbed to return a chosen message list (or a
miss / an error). We assert the mapping behavior: one turn (``HumanMessage`` up
to the next) collapses into a single assistant ``Message`` with ordered
``parts``, tool calls pair up with their ``ToolMessage`` by id, redacted
content is swapped consistently on both ``content`` and ``parts``, and
``created_at`` parses; the last-AI lookup skips tool-call turns; redaction
scan finds the latest flag and is bounded by the previous human message.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
from app.agent.text_limits import TRUNCATION_LIMIT
from app.services.agent_runner import ReasoningPart, TextPart, ToolCallPart
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class _Tuple:
    def __init__(self, messages: list[Any]) -> None:
        self.checkpoint = {"channel_values": {"messages": messages}}


class StubCheckpointer:
    """Stub checkpointer: returns a programmed tuple, a miss, or raises."""

    def __init__(
        self, messages: list[Any] | None = None, *, raises: bool = False
    ) -> None:
        self._messages = messages
        self._raises = raises

    async def aget_tuple(self, config: dict[str, Any]) -> Any:
        if self._raises:
            raise RuntimeError("checkpoint backend down")
        if self._messages is None:
            return None
        return _Tuple(self._messages)


def _history(messages: list[Any] | None, *, raises: bool = False) -> CheckpointHistory:
    return CheckpointHistory(
        StubCheckpointer(messages, raises=raises), SecurityMessages()
    )


THREAD = uuid.uuid4()


# --- raw_messages -----------------------------------------------------------


@pytest.mark.unit
async def test_raw_messages_returns_empty_on_checkpoint_miss() -> None:
    assert await _history(None).raw_messages(THREAD) == []


@pytest.mark.unit
async def test_raw_messages_returns_empty_on_backend_error() -> None:
    assert await _history(None, raises=True).raw_messages(THREAD) == []


# --- history mapping --------------------------------------------------------


@pytest.mark.unit
async def test_history_groups_a_tool_call_turn_into_one_assistant_message() -> None:
    """One turn (tool-calling AIMessage + its ToolMessage + final AIMessage)

    collapses into a single ``Message``, not three — the grouping rule this
    phase adds. ``id``/``content`` still resolve to the final, tool-call-free
    ``AIMessage`` (``a2``) — the same id ``routes/chats.py`` resolves
    ``trace_id``/``feedback_score``/``artifacts`` by, unaffected by grouping.
    """
    messages = [
        HumanMessage(content="question", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "x", "args": {"q": "v"}, "id": "c"}],
            additional_kwargs={"reasoning": "thinking about x"},
        ),
        ToolMessage(content="tool out", id="t1", tool_call_id="c", name="x"),
        AIMessage(content="answer", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [(m.role, m.content) for m in result] == [
        ("user", "question"),
        ("assistant", "answer"),
    ]
    assistant_message = result[1]
    assert assistant_message.id == "a2"
    assert assistant_message.parts == [
        ReasoningPart(content="thinking about x"),
        ToolCallPart(
            call_id="c",
            tool="x",
            args='{"q": "v"}',
            status="success",
            result_preview="tool out",
            truncated=False,
        ),
        TextPart(content="answer"),
    ]


@pytest.mark.unit
async def test_history_swaps_redacted_assistant_content() -> None:
    messages = [
        HumanMessage(content="question", id="h1"),
        AIMessage(
            content="secret leaked",
            id="a1",
            additional_kwargs={"security_redacted": True},
        ),
    ]

    result = await _history(messages).history(THREAD)

    assistant_message = result[-1]
    assert assistant_message.redacted is True
    assert assistant_message.content == SecurityMessages().redacted_user_facing
    assert assistant_message.parts == [
        TextPart(content=SecurityMessages().redacted_user_facing)
    ]


@pytest.mark.unit
async def test_history_keeps_several_tool_calls_of_one_turn_in_one_message() -> None:
    # Rendering rule (streaming.md § «История: typed parts»): one turn is one
    # assistant message whatever happened inside it, and the parts keep the
    # order the agent produced them in — that is what makes history render
    # identically to the live feed.
    messages = [
        HumanMessage(content="research this", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "search", "args": {"q": "a"}, "id": "c1"},
                {"name": "scrape", "args": {"url": "b"}, "id": "c2"},
            ],
        ),
        ToolMessage(content="hits", id="t1", tool_call_id="c1", name="search"),
        ToolMessage(content="page", id="t2", tool_call_id="c2", name="scrape"),
        AIMessage(content="summary", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [m.role for m in result] == ["user", "assistant"]
    assistant = result[1]
    assert assistant.id == "a2"
    assert [p.type for p in assistant.parts] == ["tool_call", "tool_call", "text"]
    assert [
        (p.call_id, p.tool, p.args, p.result_preview)
        for p in assistant.parts
        if isinstance(p, ToolCallPart)
    ] == [
        ("c1", "search", '{"q": "a"}', "hits"),
        ("c2", "scrape", '{"url": "b"}', "page"),
    ]


@pytest.mark.unit
async def test_history_reports_a_failed_tool_call_with_error_status() -> None:
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "search", "args": {}, "id": "c1"}],
        ),
        ToolMessage(
            content="upstream refused",
            id="t1",
            tool_call_id="c1",
            name="search",
            status="error",
        ),
        AIMessage(content="sorry", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    tool_part = next(p for p in result[1].parts if isinstance(p, ToolCallPart))
    assert tool_part.status == "error"
    assert tool_part.result_preview == "upstream refused"


@pytest.mark.unit
async def test_history_marks_an_unresolved_tool_call_as_pending() -> None:
    # The checkpoint can freeze between the call and its result (run cut short);
    # history shows how far the agent got instead of dropping the row.
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "search", "args": {}, "id": "c1"}],
        ),
    ]

    result = await _history(messages).history(THREAD)

    assistant = result[1]
    assert assistant.id == "a1"
    assert assistant.content == ""
    tool_part = next(p for p in assistant.parts if isinstance(p, ToolCallPart))
    assert (tool_part.status, tool_part.result_preview) == ("pending", "")


@pytest.mark.unit
async def test_history_truncates_oversized_args_and_result_preview() -> None:
    # Same limit as the wire (design-brief § «Лимиты»): the API must not ship a
    # megabyte of scraped page into the history payload.
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "write", "args": {"text": "x" * 5000}, "id": "c1"},
            ],
        ),
        ToolMessage(content="y" * 5000, id="t1", tool_call_id="c1", name="write"),
        AIMessage(content="done", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    tool_part = next(p for p in result[1].parts if isinstance(p, ToolCallPart))
    assert len(tool_part.args) == TRUNCATION_LIMIT
    assert len(tool_part.result_preview) == TRUNCATION_LIMIT
    assert tool_part.truncated is True


@pytest.mark.unit
async def test_history_drops_the_compaction_summary_before_the_first_turn() -> None:
    # ``_reduce_context`` prepends an id-less summary AIMessage — a context
    # digest, not a turn the user took part in, so it has no row in the feed.
    messages = [
        AIMessage(content="previous conversation summary"),
        HumanMessage(content="next question", id="h1"),
        AIMessage(content="next answer", id="a1"),
    ]

    result = await _history(messages).history(THREAD)

    assert [(m.role, m.content) for m in result] == [
        ("user", "next question"),
        ("assistant", "next answer"),
    ]


@pytest.mark.unit
async def test_history_is_empty_when_the_thread_has_no_human_message() -> None:
    assert await _history([AIMessage(content="orphan", id="a1")]).history(THREAD) == []


@pytest.mark.unit
async def test_history_separates_consecutive_turns() -> None:
    messages = [
        HumanMessage(content="q1", id="h1"),
        AIMessage(content="a1", id="ai1", additional_kwargs={"reasoning": "r1"}),
        HumanMessage(content="q2", id="h2"),
        AIMessage(content="a2", id="ai2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [(m.role, m.content) for m in result] == [
        ("user", "q1"),
        ("assistant", "a1"),
        ("user", "q2"),
        ("assistant", "a2"),
    ]
    assert result[1].parts == [
        ReasoningPart(content="r1"),
        TextPart(content="a1"),
    ]
    assert result[3].parts == [TextPart(content="a2")]


@pytest.mark.unit
async def test_history_user_messages_carry_no_parts() -> None:
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(content="a", id="a1"),
    ]

    result = await _history(messages).history(THREAD)

    assert result[0].parts == []


@pytest.mark.unit
async def test_history_redacted_turn_hides_its_reasoning_too() -> None:
    # Redaction policy is all-or-nothing: showing the "harmless" half of the
    # message that triggered the block would be a narrower policy than the one
    # already applied to ``content``.
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="secret leaked",
            id="a1",
            additional_kwargs={
                "security_redacted": True,
                "reasoning": "here is how I would leak it",
            },
        ),
    ]

    result = await _history(messages).history(THREAD)

    assert result[1].parts == [
        TextPart(content=SecurityMessages().redacted_user_facing)
    ]


@pytest.mark.unit
async def test_history_parses_created_at_timestamp() -> None:
    messages = [
        HumanMessage(
            content="hi",
            id="h1",
            additional_kwargs={"created_at": "2026-06-22T10:00:00+00:00"},
        )
    ]

    result = await _history(messages).history(THREAD)

    assert result[0].created_at is not None
    assert result[0].created_at.year == 2026


# --- last_ai_message_id -----------------------------------------------------


@pytest.mark.unit
async def test_last_ai_message_id_skips_tool_call_turns() -> None:
    messages = [
        AIMessage(content="plain", id="a1"),
        AIMessage(
            content="", id="a2", tool_calls=[{"name": "x", "args": {}, "id": "c"}]
        ),
    ]

    assert await _history(messages).last_ai_message_id(THREAD) == "a1"


@pytest.mark.unit
async def test_last_ai_message_id_none_when_no_plain_assistant() -> None:
    messages = [HumanMessage(content="hi", id="h1")]

    assert await _history(messages).last_ai_message_id(THREAD) is None


# --- latest_redaction -------------------------------------------------------


@pytest.mark.unit
async def test_latest_redaction_flags_redacted_tool_message_as_tool_result() -> None:
    messages = [
        HumanMessage(content="q", id="h1"),
        ToolMessage(
            content="[blocked]",
            id="t1",
            tool_call_id="c",
            name="x",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.CANARY.value,
            },
        ),
    ]

    hit = await _history(messages).latest_redaction(THREAD)

    assert hit is not None
    assert hit.checkpoint is Checkpoint.TOOL_RESULT
    assert hit.detection_layer is DetectionLayer.CANARY


@pytest.mark.unit
async def test_latest_redaction_flags_redacted_ai_message_as_tool_call_arg() -> None:
    messages = [
        AIMessage(
            content="",
            id="a1",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
            },
        )
    ]

    hit = await _history(messages).latest_redaction(THREAD)

    assert hit is not None
    assert hit.checkpoint is Checkpoint.TOOL_CALL_ARG


@pytest.mark.unit
async def test_latest_redaction_invalid_layer_yields_none_layer() -> None:
    messages = [
        AIMessage(
            content="",
            id="a1",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": "not-a-real-layer",
            },
        )
    ]

    hit = await _history(messages).latest_redaction(THREAD)

    assert hit is not None
    assert hit.detection_layer is None


@pytest.mark.unit
async def test_latest_redaction_scan_is_bounded_by_previous_human_message() -> None:
    # A redaction older than the latest human turn must not be reported.
    messages = [
        AIMessage(
            content="",
            id="a_old",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.CANARY.value,
            },
        ),
        HumanMessage(content="new question", id="h2"),
        AIMessage(content="clean answer", id="a_new"),
    ]

    hit = await _history(messages).latest_redaction(THREAD)

    assert hit is None


@pytest.mark.unit
async def test_latest_redaction_none_when_no_redaction_present() -> None:
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(content="clean", id="a1"),
    ]

    assert await _history(messages).latest_redaction(THREAD) is None
