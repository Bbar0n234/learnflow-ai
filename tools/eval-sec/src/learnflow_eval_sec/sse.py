"""Minimal async SSE iterator for our backend's wire format.

Backend emits one-event-per-line: `data: {"type": "...", ...}\n\n`
(see backend/app/api/routes/messages.py). No multi-line events, no id/event fields.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class SseEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


async def aiter_sse(response: httpx.Response) -> AsyncIterator[SseEvent]:
    async for raw_line in response.aiter_lines():
        line = raw_line.strip()
        if not line or line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload_str = line[len("data:") :].strip()
        if not payload_str:
            continue
        payload: dict[str, Any] = json.loads(payload_str)
        event_type = payload.pop("type", "")
        yield SseEvent(type=str(event_type), data=payload)
