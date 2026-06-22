"""format_for_classifier: conversation history -> XML-wrapped, role-prefixed text.

Pure function — no model, no I/O. The classifier feeds this string to the LLM as
the security context, so the behavior under test is "which role prefix each
message gets and that the current message is appended last", not any LLM output.
"""

from __future__ import annotations

import pytest
from app.agent.security.history_formatter import format_for_classifier
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


@pytest.mark.unit
def test_format_wraps_output_in_conversation_history_tags() -> None:
    out = format_for_classifier([], "current question")

    assert out.startswith("<conversation_history>\n")
    assert out.endswith("\n</conversation_history>")


@pytest.mark.unit
def test_format_appends_current_content_as_trailing_user_line() -> None:
    out = format_for_classifier([HumanMessage(content="earlier")], "now")

    lines = out.splitlines()
    # First inner line is the history turn, last inner line is the current input.
    assert lines[1] == "[USER] earlier"
    assert lines[-2] == "[USER] now"


@pytest.mark.unit
def test_format_prefixes_each_role() -> None:
    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
        SystemMessage(content="policy"),
    ]

    out = format_for_classifier(messages, "current")

    assert "[USER] hi" in out
    assert "[ASSISTANT] hello" in out
    # Anything that is not Human/AI/Tool falls back to the SYSTEM prefix.
    assert "[SYSTEM] policy" in out


@pytest.mark.unit
def test_format_tool_message_uses_named_prefix() -> None:
    msg = ToolMessage(content="result", tool_call_id="c1", name="web_search")

    out = format_for_classifier([msg], "current")

    assert "[TOOL:web_search] result" in out


@pytest.mark.unit
def test_format_tool_message_without_name_falls_back_to_unknown() -> None:
    msg = ToolMessage(content="result", tool_call_id="c1")

    out = format_for_classifier([msg], "current")

    assert "[TOOL:unknown] result" in out


@pytest.mark.unit
def test_format_coerces_non_string_content_to_str() -> None:
    # Multimodal content can arrive as a list of blocks; it must not crash.
    msg = HumanMessage(content=[{"type": "text", "text": "block"}])

    out = format_for_classifier([msg], "current")

    assert "[USER] [{'type': 'text', 'text': 'block'}]" in out
