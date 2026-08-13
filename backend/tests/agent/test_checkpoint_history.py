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
from app.services.agent_runner import (
    ArtifactPart,
    ReasoningPart,
    TextPart,
    ToolCallPart,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from structlog.testing import capture_logs


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
            args_truncated=False,
            status="success",
            result_preview="tool out",
            result_truncated=False,
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
    assert tool_part.result_truncated is False


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
    assert tool_part.args_truncated is True
    assert tool_part.result_truncated is True


@pytest.mark.unit
async def test_history_flags_args_and_result_truncation_independently() -> None:
    # Two independent cuts, two independent flags: a long result must not mark
    # the (intact) args as truncated, and vice versa — otherwise the consumer
    # renders a "cut by the server" marker over a zone that was never cut.
    messages = [
        HumanMessage(content="q", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "write", "args": {"text": "x"}, "id": "c1"},
                {"name": "write", "args": {"text": "x" * 5000}, "id": "c2"},
            ],
        ),
        ToolMessage(content="y" * 5000, id="t1", tool_call_id="c1", name="write"),
        ToolMessage(content="ok", id="t2", tool_call_id="c2", name="write"),
        AIMessage(content="done", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    long_result, long_args = (p for p in result[1].parts if isinstance(p, ToolCallPart))
    assert (long_result.args_truncated, long_result.result_truncated) == (False, True)
    assert (long_args.args_truncated, long_args.result_truncated) == (True, False)


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


# --- artifact parts (feat-011: the chat <-> artifact link lives here now) ----


@pytest.mark.unit
async def test_history_replays_artifact_parts_after_the_turns_final_text() -> None:
    """A tool that wrote a file replays as an ``ArtifactPart`` in the turn.

    The link "artifact ↝ chat" has no PG row behind it any more (ADR-032): the
    checkpoint's ``ToolMessage.artifact`` is the only record, and the path is
    the identity the frontend re-fetches the file by. Order is contract — the
    card is an outcome of the turn, so it trails the final text rather than
    sitting inline after the call that happened to write the file.
    """
    messages = [
        HumanMessage(content="save it", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[
                {"name": "write_file", "args": {"path": "artifacts/s.md"}, "id": "c"}
            ],
        ),
        ToolMessage(
            content="File written",
            id="t1",
            tool_call_id="c",
            name="write_file",
            artifact=[
                {"path": "s.md", "title": "s.md", "type": "md", "kind": "created"}
            ],
        ),
        AIMessage(content="saved", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    parts = result[1].parts
    assert [type(p).__name__ for p in parts] == [
        "ToolCallPart",
        "TextPart",
        "ArtifactPart",
    ]
    assert parts[2] == ArtifactPart(
        path="s.md", title="s.md", type="md", kind="created", diff=None
    )


@pytest.mark.unit
async def test_history_replays_an_updated_artifact_with_its_line_counters() -> None:
    messages = [
        HumanMessage(content="fix it", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "write_file", "args": {}, "id": "c"}],
        ),
        ToolMessage(
            content="File written",
            id="t1",
            tool_call_id="c",
            name="write_file",
            artifact=[
                {
                    "path": "s.md",
                    "title": "s.md",
                    "type": "md",
                    "kind": "updated",
                    "diff": {"added": 3, "removed": 1},
                }
            ],
        ),
        AIMessage(content="done", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    artifact_parts = [p for p in result[1].parts if isinstance(p, ArtifactPart)]
    assert artifact_parts[0].kind == "updated"
    assert artifact_parts[0].diff == {"added": 3, "removed": 1}


@pytest.mark.unit
async def test_history_replays_one_artifact_part_per_file_a_job_touched() -> None:
    # A render job writes several files in one call — each one is its own card.
    messages = [
        HumanMessage(content="render", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "run_command", "args": {}, "id": "c"}],
        ),
        ToolMessage(
            content="exit_code: 0",
            id="t1",
            tool_call_id="c",
            name="run_command",
            artifact=[
                {"path": "a.md", "title": "a.md", "type": "md", "kind": "created"},
                {"path": "b.png", "title": "b.png", "type": "png", "kind": "created"},
            ],
        ),
        AIMessage(content="done", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [p.path for p in result[1].parts if isinstance(p, ArtifactPart)] == [
        "a.md",
        "b.png",
    ]


@pytest.mark.unit
async def test_history_groups_artifacts_of_several_calls_at_the_end_of_the_turn() -> (
    None
):
    # Cards of a multi-call turn arrive as one trailing group, not interleaved
    # with the activity feed — the reader sees the turn's outcome in one place.
    messages = [
        HumanMessage(content="do both", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "write_file", "args": {}, "id": "c1"}],
        ),
        ToolMessage(
            content="File written",
            id="t1",
            tool_call_id="c1",
            name="write_file",
            artifact=[
                {"path": "a.md", "title": "a.md", "type": "md", "kind": "created"}
            ],
        ),
        AIMessage(
            content="",
            id="a2",
            tool_calls=[{"name": "execute_code", "args": {}, "id": "c2"}],
        ),
        ToolMessage(
            content="exit_code: 0",
            id="t2",
            tool_call_id="c2",
            name="execute_code",
            artifact=[
                {"path": "p.png", "title": "p.png", "type": "png", "kind": "created"}
            ],
        ),
        AIMessage(content="ready", id="a3"),
    ]

    result = await _history(messages).history(THREAD)

    assert [type(p).__name__ for p in result[1].parts] == [
        "ToolCallPart",
        "ToolCallPart",
        "TextPart",
        "ArtifactPart",
        "ArtifactPart",
    ]


@pytest.mark.unit
async def test_history_collapses_a_path_written_twice_in_one_turn() -> None:
    """One card per path — and a file created here stays "created".

    A job that rewrites what an earlier call in the same turn created would
    otherwise produce two cards for one file, the second of them labelled
    "updated" — which reads as "your existing file changed" for a file that
    did not exist before this turn.
    """
    messages = [
        HumanMessage(content="build it", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "write_file", "args": {}, "id": "c1"}],
        ),
        ToolMessage(
            content="File written",
            id="t1",
            tool_call_id="c1",
            name="write_file",
            artifact=[
                {"path": "r.md", "title": "r.md", "type": "md", "kind": "created"}
            ],
        ),
        AIMessage(
            content="",
            id="a2",
            tool_calls=[{"name": "execute_code", "args": {}, "id": "c2"}],
        ),
        ToolMessage(
            content="exit_code: 0",
            id="t2",
            tool_call_id="c2",
            name="execute_code",
            artifact=[
                {
                    "path": "r.md",
                    "title": "r.md",
                    "type": "md",
                    "kind": "updated",
                    "diff": {"added": 4, "removed": 0},
                }
            ],
        ),
        AIMessage(content="done", id="a3"),
    ]

    result = await _history(messages).history(THREAD)

    artifact_parts = [p for p in result[1].parts if isinstance(p, ArtifactPart)]
    assert artifact_parts == [
        ArtifactPart(
            path="r.md",
            title="r.md",
            type="md",
            kind="created",
            diff={"added": 4, "removed": 0},
        )
    ]


@pytest.mark.unit
async def test_history_of_a_legacy_dict_artifact_renders_the_turn_without_cards() -> (
    None
):
    """A checkpoint written before this iteration must not 500 the whole chat.

    ``create_artifact``/``generate_image`` used to key ``ToolMessage.artifact``
    as a single ``dict``; the file model reads it as a *list*, and iterating a
    dict yields its string keys — ``item.get(...)`` on a ``str`` raises, and
    nothing between here and ``GET /chats/{thread_id}`` catches it, so every
    thread that ever called those tools would answer 500. ADR-032 designs no
    history back-compat, so the contract is degradation, not migration: zero
    artifact parts, the rest of the turn intact.
    """
    messages = [
        HumanMessage(content="save it", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "create_artifact", "args": {}, "id": "c"}],
        ),
        ToolMessage(
            content="Artifact created",
            id="t1",
            tool_call_id="c",
            name="create_artifact",
            artifact={"id": "uuid-1", "title": "T", "type": "md"},
        ),
        AIMessage(content="saved", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [type(p).__name__ for p in result[1].parts] == ["ToolCallPart", "TextPart"]
    assert not [p for p in result[1].parts if isinstance(p, ArtifactPart)]


@pytest.mark.unit
async def test_history_records_a_warning_for_a_legacy_dict_artifact() -> None:
    # Silent skipping would make "old chat lost its artifact cards" invisible;
    # the tool_call_id is what ties the line back to a concrete checkpoint.
    messages = [
        HumanMessage(content="save it", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "create_artifact", "args": {}, "id": "c"}],
        ),
        ToolMessage(
            content="Artifact created",
            id="t1",
            tool_call_id="c",
            name="create_artifact",
            artifact={"id": "uuid-1", "title": "T", "type": "md"},
        ),
    ]

    with capture_logs() as logs:
        await _history(messages).history(THREAD)

    assert [
        (entry["event"], entry["log_level"], entry["tool_call_id"])
        for entry in logs
        if entry["event"] == "legacy non-list ToolMessage.artifact skipped"
    ] == [("legacy non-list ToolMessage.artifact skipped", "warning", "c")]


@pytest.mark.unit
async def test_history_gives_a_tool_call_without_files_no_artifact_part() -> None:
    messages = [
        HumanMessage(content="run", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "run_command", "args": {}, "id": "c"}],
        ),
        ToolMessage(
            content="exit_code: 0", id="t1", tool_call_id="c", name="run_command"
        ),
        AIMessage(content="done", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert not [p for p in result[1].parts if isinstance(p, ArtifactPart)]


# --- attachments (the input-side mirror of ArtifactPart) --------------------


@pytest.mark.unit
async def test_history_returns_the_users_own_text_without_the_attachment_note() -> None:
    """The note is model-facing only; the UI renders chips from metadata.

    Backend appends "[Attached files: …]" to what the model sees and keeps the
    clean text plus the ``{path, title}`` list in ``additional_kwargs`` — so a
    reloaded chat shows neither a duplicated note nor a lost chip.
    """
    messages = [
        HumanMessage(
            content="summarize it\n\n[Attached files: uploads/lecture.pdf]",
            id="h1",
            additional_kwargs={
                "text": "summarize it",
                "attachments": [
                    {"path": "uploads/lecture.pdf", "title": "lecture.pdf"}
                ],
            },
        ),
        AIMessage(content="sure", id="a1"),
    ]

    result = await _history(messages).history(THREAD)

    assert result[0].content == "summarize it"
    assert [(a.path, a.title) for a in result[0].attachments] == [
        ("uploads/lecture.pdf", "lecture.pdf")
    ]


@pytest.mark.unit
async def test_history_of_a_message_without_attachments_reports_none() -> None:
    messages = [
        HumanMessage(content="plain question", id="h1"),
        AIMessage(content="answer", id="a1"),
    ]

    result = await _history(messages).history(THREAD)

    assert result[0].content == "plain question"
    assert result[0].attachments == []
