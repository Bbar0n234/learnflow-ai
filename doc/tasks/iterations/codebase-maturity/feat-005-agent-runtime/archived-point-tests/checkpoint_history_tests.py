"""feat-005: CheckpointHistory — checkpointer reads/mapping (concern 3)."""

import asyncio
import uuid
from types import SimpleNamespace

from app.agent.checkpoint_history import CheckpointHistory
from app.agent.security.types import Checkpoint, DetectionLayer, SecurityMessages
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

_MESSAGES = SecurityMessages()
_TID = uuid.uuid4()


class _FakeCheckpointer:
    def __init__(self, messages: list | None) -> None:
        self._messages = messages

    async def aget_tuple(self, config):
        if self._messages is None:
            return None
        return SimpleNamespace(
            checkpoint={"channel_values": {"messages": self._messages}}
        )


def _history(messages: list | None) -> CheckpointHistory:
    return CheckpointHistory(_FakeCheckpointer(messages), _MESSAGES)


def test_raw_messages_empty_when_no_checkpoint() -> None:
    assert asyncio.run(_history(None).raw_messages(_TID)) == []


def test_history_maps_and_skips_tool_turns() -> None:
    messages = [
        HumanMessage(content="hello", id="h1"),
        AIMessage(
            content="",
            id="a1",
            tool_calls=[{"name": "t", "args": {}, "id": "c1", "type": "tool_call"}],
        ),
        AIMessage(content="answer", id="a2"),
    ]
    result = asyncio.run(_history(messages).history(_TID))
    assert [(m.role, m.content) for m in result] == [
        ("user", "hello"),
        ("assistant", "answer"),
    ]


def test_history_applies_redaction() -> None:
    messages = [
        AIMessage(
            content="secret leaked",
            id="a1",
            additional_kwargs={"security_redacted": True},
        )
    ]
    result = asyncio.run(_history(messages).history(_TID))
    assert result[0].redacted is True
    assert result[0].content == _MESSAGES.redacted_user_facing


def test_last_ai_message_id_skips_tool_calls() -> None:
    messages = [
        AIMessage(content="answer", id="a1"),
        AIMessage(
            content="",
            id="a2",
            tool_calls=[{"name": "t", "args": {}, "id": "c1", "type": "tool_call"}],
        ),
    ]
    assert asyncio.run(_history(messages).last_ai_message_id(_TID)) == "a1"


def test_latest_redaction_maps_tool_message_to_tool_result() -> None:
    messages = [
        HumanMessage(content="q", id="h1"),
        ToolMessage(
            content="[blocked]",
            name="get_section",
            tool_call_id="c1",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
            },
        ),
    ]
    hit = asyncio.run(_history(messages).latest_redaction(_TID))
    assert hit is not None
    assert hit.checkpoint == Checkpoint.TOOL_RESULT
    assert hit.detection_layer == DetectionLayer.LLM_CLASSIFIER


def test_latest_redaction_maps_ai_message_to_tool_call_arg() -> None:
    messages = [
        AIMessage(
            content="",
            id="a1",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
            },
        ),
    ]
    hit = asyncio.run(_history(messages).latest_redaction(_TID))
    assert hit is not None
    assert hit.checkpoint == Checkpoint.TOOL_CALL_ARG


def test_latest_redaction_none_when_clean() -> None:
    messages = [HumanMessage(content="q", id="h1"), AIMessage(content="a", id="a1")]
    assert asyncio.run(_history(messages).latest_redaction(_TID)) is None


def test_latest_redaction_bounded_by_human_message() -> None:
    # A redaction from a PREVIOUS turn must be ignored: the scan stops at the
    # most recent HumanMessage.
    messages = [
        AIMessage(
            content="",
            id="a0",
            additional_kwargs={
                "security_redacted": True,
                "original_detection_layer": DetectionLayer.LLM_CLASSIFIER.value,
            },
        ),
        HumanMessage(content="new turn", id="h1"),
        AIMessage(content="clean answer", id="a1"),
    ]
    assert asyncio.run(_history(messages).latest_redaction(_TID)) is None
