from __future__ import annotations

from typing import Any

from app.agent.security.detectors.base import Hit
from app.agent.security.detectors.normalize import normalize
from app.agent.security.types import Checkpoint, DetectionLayer


class PairedToolIdentifierDetector:
    """Detects leakage of PROTECTED internal tool identifiers.

    A tool is considered "compromised" when BOTH its normalized name AND
    at least ``min_params_per_tool`` of its parameter names appear in the
    buffer. INJECTION is raised when ``|compromised tools| >=
    min_compromised_tools``.

    The registry intentionally covers only internal non-MCP tools (our
    PROTECTED surface, per design-brief §3.2). MCP tool identifiers are
    DISCLOSABLE and not tracked here.
    """

    name = "paired"
    layer = DetectionLayer.PAIRED
    applies_to = frozenset(
        {
            Checkpoint.FINAL_OUTPUT,
            Checkpoint.TOOL_CALL_ARG,
        }
    )

    def __init__(
        self,
        registry: dict[str, list[str]],
        *,
        min_compromised_tools: int = 3,
        min_params_per_tool: int = 1,
    ) -> None:
        self._min_compromised_tools = min_compromised_tools
        self._min_params_per_tool = min_params_per_tool
        self._registry: dict[str, list[str]] = {
            normalize(tool): [normalize(p) for p in params]
            for tool, params in registry.items()
            if tool
        }

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None:
        if not buffer or not self._registry:
            return None
        canonical = normalize(buffer)
        compromised: list[str] = []
        for tool_name, params in self._registry.items():
            if tool_name not in canonical:
                continue
            param_hits = sum(1 for p in params if p and p in canonical)
            if param_hits >= self._min_params_per_tool:
                compromised.append(tool_name)
                if len(compromised) >= self._min_compromised_tools:
                    return Hit(
                        layer=self.layer,
                        details={"compromised_tools": compromised},
                    )
        return None
