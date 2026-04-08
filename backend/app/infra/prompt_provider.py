from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from jinja2 import Template

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = structlog.get_logger()


class PromptProvider:
    """Fetches prompts from Langfuse with file fallback.

    Infra-level component. Uses Langfuse SDK's built-in cache (TTL-based).
    On cache miss the SDK makes a sync HTTP call — acceptable at current scale.
    """

    def __init__(
        self,
        langfuse: Langfuse | None,
        label: str,
        cache_ttl: int,
        prompts_dir: Path,
    ) -> None:
        self._langfuse = langfuse
        self._label = label
        self._cache_ttl = cache_ttl
        self._prompts_dir = prompts_dir
        self._prompt_cache: dict[str, Any] = {}

    def _qualified(self, name: str) -> str:
        return f"{name}--{self._label}"

    def get_prompt(self, name: str, **variables: str) -> str:
        if self._langfuse:
            try:
                prompt = self._langfuse.get_prompt(
                    self._qualified(name),
                    label="latest",
                    cache_ttl_seconds=self._cache_ttl,
                    fallback=self._load_file(name),
                )
                self._prompt_cache[name] = prompt
                return prompt.compile(**variables)
            except Exception:
                logger.warning(
                    "prompt fetch failed, using file fallback",
                    name=name,
                    exc_info=True,
                )
        text = self._load_file(name)
        if variables:
            return Template(text).render(**variables)
        return text

    def get_config(self, name: str) -> dict[str, Any] | None:
        cached = self._prompt_cache.get(name)
        if cached is not None:
            return cached.config
        return None

    def _load_file(self, name: str) -> str:
        path = self._prompts_dir / f"{name}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("prompt file not found", path=str(path))
        return ""
