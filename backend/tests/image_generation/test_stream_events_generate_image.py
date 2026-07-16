"""Unit: ``StreamEventMapper`` extension for ``generate_image`` (T1.5).

The SSE mapper emits ``artifact_created`` for the ``create_artifact`` tool; this
iteration extends it to ``generate_image`` with the same event shape (the
``type`` -> ``artifact_type`` remap). These assert the *new* tool name flows
through unchanged — the ``create_artifact`` path is covered in
``tests/agent/test_stream_events.py``.
"""

from __future__ import annotations

import pytest
from app.agent.stream_events import StreamEventMapper
from langchain_core.messages import ToolMessage

pytestmark = pytest.mark.unit


@pytest.fixture
def mapper() -> StreamEventMapper:
    return StreamEventMapper()


def test_generate_image_emits_artifact_created_with_remapped_type(
    mapper: StreamEventMapper,
) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(
                    content="Image saved: 'Cover'",
                    tool_call_id="c1",
                    name="generate_image",
                    artifact={"type": "image", "id": "a1", "title": "Cover"},
                )
            ]
        }
    }

    events = mapper.updates(data)

    assert [e.type for e in events] == ["tool_end", "artifact_created"]
    artifact_event = events[1]
    assert artifact_event.data["artifact_type"] == "image"
    assert "type" not in artifact_event.data
    assert artifact_event.data["id"] == "a1"
    assert artifact_event.data["title"] == "Cover"


def test_generate_image_without_artifact_payload_only_emits_tool_end(
    mapper: StreamEventMapper,
) -> None:
    data = {
        "tools": {
            "messages": [
                ToolMessage(content="err", tool_call_id="c1", name="generate_image")
            ]
        }
    }

    events = mapper.updates(data)

    # Tool error path: tool_end fires (placeholder clears), no artifact_created.
    assert [e.type for e in events] == ["tool_end"]
