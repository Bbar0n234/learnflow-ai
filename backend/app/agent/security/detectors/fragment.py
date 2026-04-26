from __future__ import annotations

from typing import Any

from app.agent.security.detectors.base import Hit
from app.agent.security.detectors.normalize import normalize
from app.agent.security.types import Checkpoint, DetectionLayer


class FragmentDetector:
    """Sliding-window substring match against the PROTECTED corpus.

    Fragments that echo ≥ ``min_unique_matches`` distinct windows from the
    corpus (hardening preamble + security instructions + internal tool
    descriptions + skills) trigger INJECTION. MCP descriptions and
    user-owned content are NOT in the corpus.
    """

    name = "fragment"
    layer = DetectionLayer.FRAGMENT
    applies_to = frozenset(
        {
            Checkpoint.USER_INPUT,
            Checkpoint.TOOL_RESULT,
            Checkpoint.FINAL_OUTPUT,
            Checkpoint.TOOL_CALL_ARG,
        }
    )

    def __init__(
        self,
        corpus_texts: list[str],
        *,
        window_size: int = 60,
        stride: int = 30,
        min_unique_matches: int = 2,
    ) -> None:
        self._window_size = window_size
        self._stride = stride
        self._min_unique_matches = min_unique_matches
        self._windows = self._build_corpus_windows(corpus_texts)

    def _build_corpus_windows(self, corpus_texts: list[str]) -> frozenset[str]:
        windows: set[str] = set()
        for text in corpus_texts:
            if not text:
                continue
            canonical = normalize(text)
            if len(canonical) < self._window_size:
                if canonical:
                    windows.add(canonical)
                continue
            i = 0
            while i + self._window_size <= len(canonical):
                windows.add(canonical[i : i + self._window_size])
                i += self._stride
        return frozenset(windows)

    def inspect(self, buffer: str, ctx: dict[str, Any]) -> Hit | None:
        if not buffer or not self._windows:
            return None
        canonical = normalize(buffer)
        if len(canonical) < self._window_size:
            return None
        unique_hits: set[str] = set()
        i = 0
        while i + self._window_size <= len(canonical):
            w = canonical[i : i + self._window_size]
            if w in self._windows:
                unique_hits.add(w)
                if len(unique_hits) >= self._min_unique_matches:
                    return Hit(
                        layer=self.layer,
                        details={"matched_windows": len(unique_hits)},
                    )
            i += self._stride
        return None
