from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from app.agent.security.types import Checkpoint, DetectionLayer


class Hit(BaseModel):
    layer: DetectionLayer
    details: dict[str, Any] = {}


class DeterministicDetector(Protocol):
    name: str
    applies_to: frozenset[Checkpoint]
    layer: DetectionLayer

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None: ...
