"""Unit: ``CheckpointHistory`` — read-side adapter over the checkpointer.

The only collaborator is the checkpointer; it is болезненная граница (real one is
Postgres/in-memory infra), so it is stubbed to return a chosen message list (or a
miss / an error). We assert the mapping behavior: history excludes tool-call
turns, swaps redacted content, parses ``created_at``; the last-AI lookup skips
tool-call turns; redaction scan finds the latest flag and is bounded by the
previous human message.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
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
async def test_history_maps_human_and_assistant_and_excludes_tool_turns() -> None:
    messages = [
        HumanMessage(content="question", id="h1"),
        AIMessage(
            content="", id="a1", tool_calls=[{"name": "x", "args": {}, "id": "c"}]
        ),
        ToolMessage(content="tool out", id="t1", tool_call_id="c", name="x"),
        AIMessage(content="answer", id="a2"),
    ]

    result = await _history(messages).history(THREAD)

    assert [(m.role, m.content) for m in result] == [
        ("user", "question"),
        ("assistant", "answer"),
    ]


@pytest.mark.unit
async def test_history_swaps_redacted_assistant_content() -> None:
    messages = [
        AIMessage(
            content="secret leaked",
            id="a1",
            additional_kwargs={"security_redacted": True},
        )
    ]

    result = await _history(messages).history(THREAD)

    assert result[0].redacted is True
    assert result[0].content == SecurityMessages().redacted_user_facing


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
