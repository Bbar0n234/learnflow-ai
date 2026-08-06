from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from jinja2 import Template

if TYPE_CHECKING:
    from langfuse import Langfuse

logger = structlog.get_logger()

# Langfuse's own mustache-style substitution (`TemplateParser`) — a
# single left-to-right pass that only replaces names it was given a value
# for, never re-scanning what it just inserted. We mirror that exact
# `{{ name }}` shape here to read the *template source*, not the rendered
# output: composed prompt text can carry user-controlled content (custom
# instructions, user-installed MCP tool descriptions, classified user
# messages) that may itself spell out a literal ``{{ some_slot_name }}``.
# Scanning post-render text for leftover braces would flag that as a false
# "unresolved placeholder"; scanning the template source before
# substitution never sees user content at all.
_MUSTACHE_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _unresolved_placeholders(
    template_text: str, variables: dict[str, str]
) -> list[str]:
    """Slot names the template declares that ``variables`` doesn't cover."""
    declared = dict.fromkeys(_MUSTACHE_PLACEHOLDER_RE.findall(template_text))
    return [name for name in declared if name not in variables]


def _warn_unresolved_placeholders(
    name: str, template_text: str, variables: dict[str, str]
) -> None:
    """Log (never raise) any slot the template names but nothing filled in.

    Typically means a Langfuse-hosted prompt is stale (startup seed failed,
    see ``_seed_prompts`` WARNING) relative to a code-side slot rename — the
    old template still references a name the caller stopped passing.
    Content is still returned as-is: changing the startup failure mode is a
    separate, architect-level decision.
    """
    for placeholder in _unresolved_placeholders(template_text, variables):
        logger.error(
            "unresolved placeholder in rendered prompt",
            name=name,
            placeholder=placeholder,
        )


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
                    fallback=self.load_file(name),
                )
                self._prompt_cache[name] = prompt
                _warn_unresolved_placeholders(name, prompt.prompt, variables)
                return prompt.compile(**variables)
            except Exception:
                logger.warning(
                    "prompt fetch failed, using file fallback",
                    name=name,
                    exc_info=True,
                )
        text = self.load_file(name)
        if variables:
            _warn_unresolved_placeholders(name, text, variables)
            return Template(text).render(**variables)
        return text

    def get_config(self, name: str) -> dict[str, Any] | None:
        cached = self._prompt_cache.get(name)
        if cached is not None:
            return cached.config
        return None

    def load_file(self, name: str) -> str:
        path = self._prompts_dir / f"{name}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("prompt file not found", path=str(path))
        return ""
