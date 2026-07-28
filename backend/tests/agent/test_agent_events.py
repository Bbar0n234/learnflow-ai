"""Unit: ``emit_agent_event`` — the custom-channel emission helper.

Every tool that performs a domain write (KS section, user memory, skill
context) and the compaction step report through this one helper, so it has to
be safe to call from anywhere: inside the main graph, inside a subagent's tool
(where the writer is handed over explicitly), and outside any graph runtime at
all — the last case is what every direct ``tool.ainvoke`` in the test suite
does, and a raised ``KeyError`` there would turn an observability feature into
a crash (streaming.md § «agent_event», conventions/agent.md § «Добавляешь
инструмент агенту»).

The three writer sources are ordered, and this suite pins the two observable
ends of that order: an explicitly handed-over writer receives the event, and no
writer at all is a silent no-op. That the explicit writer *wins over* a live
``get_stream_writer()`` needs a real graph runtime and is covered end-to-end in
``tests/subagents/test_subagent_lifecycle_events.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from app.agent.agent_events import (
    DOMAIN_AGENT_EVENT_KINDS,
    SUBAGENT_PARENT_CALL_ID,
    SUBAGENT_STREAM_WRITER,
    emit_agent_event,
)
from app.agent.text_limits import TRUNCATION_LIMIT

pytestmark = pytest.mark.unit


class _RecordingWriter:
    """Stand-in for LangGraph's stream writer: records what was written."""

    def __init__(self) -> None:
        self.written: list[Any] = []

    def __call__(self, item: Any) -> None:
        self.written.append(item)


@contextmanager
def _subagent_scope(
    writer: _RecordingWriter | None = None, parent_call_id: str | None = None
) -> Iterator[None]:
    """Mimic the subagent wrapper's contextvar scope, reset on exit."""
    writer_token = SUBAGENT_STREAM_WRITER.set(writer)
    parent_token = SUBAGENT_PARENT_CALL_ID.set(parent_call_id)
    try:
        yield
    finally:
        SUBAGENT_STREAM_WRITER.reset(writer_token)
        SUBAGENT_PARENT_CALL_ID.reset(parent_token)


def test_emitting_outside_any_graph_runtime_is_a_silent_noop() -> None:
    # A bare tool call in a unit test has no Pregel runtime; the helper must
    # degrade to a no-op instead of raising KeyError('__pregel_runtime').
    emit_agent_event("compaction", {})


def test_explicitly_handed_over_writer_receives_the_event() -> None:
    writer = _RecordingWriter()

    with _subagent_scope(writer):
        emit_agent_event("sphere_write", {"section_id": "s1"})

    assert writer.written == [{"type": "sphere_write", "payload": {"section_id": "s1"}}]


def test_event_carries_parent_call_id_while_a_subagent_tool_is_running() -> None:
    # A domain tool has no idea it runs under a subagent; the attribution to
    # the nested feed row comes from the context it was called in.
    writer = _RecordingWriter()

    with _subagent_scope(writer, parent_call_id="outer-1"):
        emit_agent_event("memory_write", {"key": "prefers_ru"})

    assert writer.written == [
        {
            "type": "memory_write",
            "payload": {"key": "prefers_ru"},
            "parent_call_id": "outer-1",
        }
    ]


def test_event_has_no_parent_call_id_outside_a_subagent_call() -> None:
    writer = _RecordingWriter()

    with _subagent_scope(writer):
        emit_agent_event("skill_context_write", {"skill_name": "s", "key": "k"})

    assert "parent_call_id" not in writer.written[0]


@pytest.mark.parametrize("kind", sorted(DOMAIN_AGENT_EVENT_KINDS))
def test_every_documented_domain_kind_is_accepted(kind: str) -> None:
    # The four kinds of streaming.md § «Состав событий» are the emitter's and
    # the runner's shared vocabulary — none of them may be rejected here.
    writer = _RecordingWriter()

    with _subagent_scope(writer):
        emit_agent_event(kind, {})

    assert writer.written[0]["type"] == kind


def test_an_undocumented_kind_is_rejected() -> None:
    # The runner only wraps the documented kinds; anything else would be
    # passed through as a top-level wire event of that name, so the mistake is
    # caught at the emitting site instead of leaking onto the wire.
    with pytest.raises(ValueError, match="unknown agent_event kind"):
        emit_agent_event("bogus_write", {})


def test_oversized_string_payload_values_are_truncated() -> None:
    writer = _RecordingWriter()

    with _subagent_scope(writer):
        emit_agent_event("sphere_write", {"section_id": "s" * (TRUNCATION_LIMIT * 2)})

    assert len(writer.written[0]["payload"]["section_id"]) == TRUNCATION_LIMIT


def test_non_string_payload_values_reach_the_writer_unchanged() -> None:
    writer = _RecordingWriter()

    with _subagent_scope(writer):
        emit_agent_event("compaction", {"messages": 12, "keys": ["a", "b"]})

    assert writer.written[0]["payload"] == {"messages": 12, "keys": ["a", "b"]}
