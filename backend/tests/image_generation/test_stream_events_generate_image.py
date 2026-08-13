"""Unit: the wire envelopes for ``generate_image``.

``artifact_created`` follows ``response_format="content_and_artifact"``, so
``generate_image`` gets the same event shape as ``create_artifact`` (the
``type`` -> ``artifact_type`` remap, and — since T1.2 — a single-element
``artifact`` list). These assert the tool's own shape flows through
unchanged — the general list/``artifact_updated`` mechanics and the reporter
that pairs the two envelopes are covered in ``tests/agent/test_stream_events.py``.
"""

from __future__ import annotations

import pytest
from app.agent.stream_events import artifact_envelopes, tool_result_envelope
from langchain_core.messages import ToolMessage

pytestmark = pytest.mark.unit


def test_generate_image_yields_an_artifact_envelope_with_remapped_type() -> None:
    message = ToolMessage(
        content="Image saved: 'Cover'",
        tool_call_id="c1",
        name="generate_image",
        artifact=[{"type": "image", "id": "a1", "title": "Cover", "kind": "created"}],
    )

    envelopes = artifact_envelopes(message)

    assert len(envelopes) == 1
    envelope = envelopes[0]
    assert envelope["type"] == "artifact_created"
    assert envelope["data"]["artifact_type"] == "image"
    assert "type" not in envelope["data"]
    assert envelope["data"]["id"] == "a1"
    assert envelope["data"]["title"] == "Cover"


def test_generate_image_without_artifact_payload_yields_only_a_result() -> None:
    message = ToolMessage(content="err", tool_call_id="c1", name="generate_image")

    # Tool error path: the result envelope still fires (the placeholder in the
    # feed clears), no artifact envelope follows it.
    assert tool_result_envelope(message)["type"] == "tool_result"
    assert artifact_envelopes(message) == []
