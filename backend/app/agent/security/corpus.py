"""Collect PROTECTED corpus for FragmentDetector + tool registry for PairedDetector.

Only internal non-MCP material is collected. User-owned content (KS, custom
instructions, memory) and MCP descriptions are DISCLOSABLE and excluded.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool


def collect_tool_registry(tools: list[Any]) -> dict[str, list[str]]:
    """Map each internal tool name to its parameter names (from JSON schema)."""
    registry: dict[str, list[str]] = {}
    for t in tools:
        if not isinstance(t, BaseTool):
            continue
        name = t.name
        if not name:
            continue
        params: list[str] = []
        try:
            schema = t.args_schema
            if schema is None:
                params = []
            elif isinstance(schema, dict):
                props = schema.get("properties") or {}
                params = list(props.keys())
            else:
                # Pydantic-v2 BaseModel
                model_fields = getattr(schema, "model_fields", None)
                if model_fields:
                    params = list(model_fields.keys())
        except Exception:
            params = []
        registry[name] = params
    return registry


def collect_fragment_corpus(
    *,
    system_prompt: str,
    guard_classifier_prompt: str,
    internal_tools: list[Any],
    security_preamble: str,
) -> list[str]:
    """Collect the corpus FragmentDetector should window-match against.

    Sources:
      - system prompt (base text) — security instructions minus the hardening
        preamble, which lives in ``prompt_fragments.yaml`` and is composed at
        runtime, not in the template file
      - security preamble (from ``PromptFragmentsConfig.security_preamble``,
        the same object composition uses) — hardening preamble text. Required
        without a default on purpose: a caller that forgets to wire it would
        silently drop the preamble from detection, so the omission has to be a
        type error. Defense off means passing the empty string explicitly.
      - guard-classifier prompt — security instructions
      - internal non-MCP tool descriptions — PROTECTED identifiers

    Skills (SKILL.md) are NOT included: they are content of a trusted internal
    tool (`load_skill`) that legitimately surfaces the same text to the agent
    on every call. Including skills produced TOOL_RESULT fragment FP on benign
    multi-turn flows.
    """
    parts: list[str] = []
    if system_prompt:
        parts.append(system_prompt)
    if security_preamble:
        parts.append(security_preamble)
    if guard_classifier_prompt:
        parts.append(guard_classifier_prompt)

    for t in internal_tools:
        if not isinstance(t, BaseTool):
            continue
        desc = getattr(t, "description", "") or ""
        if desc:
            parts.append(desc)

    return parts
