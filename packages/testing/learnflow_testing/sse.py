"""Helpers for asserting on Server-Sent Events streams.

Collect events from an ``httpx`` streaming response (async ASGI client with
``.stream()``) into a list of ``(event, data)`` pairs for plain assertions.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class SSEvent:
    event: str
    data: str

    def json(self) -> Any:
        return json.loads(self.data)


def parse_sse(text: str) -> list[SSEvent]:
    """Parse a full SSE payload (already-collected text) into events."""
    events: list[SSEvent] = []
    event_name = "message"
    data_lines: list[str] = []
    for line in text.splitlines():
        if line == "":
            if data_lines:
                events.append(SSEvent(event_name, "\n".join(data_lines)))
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].lstrip())
    if data_lines:
        events.append(SSEvent(event_name, "\n".join(data_lines)))
    return events


async def collect_sse(response: httpx.Response) -> list[SSEvent]:
    """Drain a streaming SSE response into a list of events.

    Use with ``async with client.stream("POST", url, ...) as response:``.
    """
    chunks: list[str] = []
    async for chunk in response.aiter_text():
        chunks.append(chunk)
    return parse_sse("".join(chunks))


async def collect_event_stream(events: AsyncIterator[Any]) -> list[Any]:
    """Collect any async event iterator (e.g. ``astream_events``) into a list."""
    return [event async for event in events]
