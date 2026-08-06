"""Builds the system message + trust-boundary wrappers for LLM composition.

Langfuse's template engine supports only string substitution ({{ var }}),
so any conditional logic is done here (in Python) and the resulting section
strings are passed to ``prompt_provider.get_prompt`` as slots.

All XML wrappers and their header texts are sourced from
``configs/prompt_fragments.yaml`` via ``PromptFragmentsConfig`` so they can
be edited without a code change.

Stored messages (in the checkpointer) are kept clean — wrapping happens only
at the LLM composition boundary via ``compose_for_llm``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from app.agent.config import PromptFragmentsConfig


def _wrap_section(fragments: PromptFragmentsConfig, key: str, body: str) -> str:
    pair = fragments.open_close(key)
    if not pair:
        return body
    open_tag, close_tag = pair
    return f"{open_tag}\n{body}\n{close_tag}"


def render_canary_section(fragments: PromptFragmentsConfig, token: str) -> str:
    if not token:
        return ""
    prefix = fragments.headers.get("canary_prefix", "Internal verification token: ")
    return f"\n{prefix}{token}"


def render_security_preamble_section(
    fragments: PromptFragmentsConfig, canary_token: str
) -> str:
    """Compose the hardening-preamble slot: preamble text + canary line.

    Section = preamble text + canary line, applied literally (design-brief
    § 1 "Композиция преамбулы"): the canary line is appended whenever
    ``canary_token`` is non-empty, independently of whether the preamble
    text itself is empty — no additional coupling between the two. No
    nested templating: plain string concatenation, the leading ``\\n``
    already comes from ``render_canary_section``.
    """
    return fragments.security_preamble + render_canary_section(fragments, canary_token)


def render_custom_instructions_section(
    fragments: PromptFragmentsConfig, content: str
) -> str:
    if not content:
        return ""
    header = fragments.headers.get("custom_instructions", "").strip()
    body = f"{header}\n{content}" if header else content
    return _wrap_section(fragments, "custom_instructions", body)


def render_user_memory_section(fragments: PromptFragmentsConfig, index: str) -> str:
    if not index:
        return ""
    return _wrap_section(fragments, "user_memory", index)


def render_knowledge_sphere_section(
    fragments: PromptFragmentsConfig, index: str
) -> str:
    body = index if index else "(empty)"
    return _wrap_section(fragments, "knowledge_sphere", body)


def render_skills_section(fragments: PromptFragmentsConfig, index: str) -> str:
    if not index:
        return ""
    return _wrap_section(fragments, "available_skills", index)


def render_user_installed_mcp_section(
    fragments: PromptFragmentsConfig, tools: list[dict[str, str]]
) -> str:
    if not tools:
        return ""
    header = fragments.headers.get("user_installed_mcp", "").strip()
    parts: list[str] = []
    if header:
        parts.append(header)
    for tool in tools:
        description = tool.get("description") or ""
        parts.append(fragments.wrap("untrusted_tool_description", description))
    body = "\n".join(parts)
    return _wrap_section(fragments, "user_installed_mcp_tools", body)


def build_system_message(
    prompt_provider: Any,
    fragments: PromptFragmentsConfig,
    *,
    ks_index: str,
    skills_index: str = "",
    custom_instructions: str = "",
    user_memory_index: str = "",
    canary_token: str = "",
    user_installed_mcp_tools: list[dict[str, str]] | None = None,
) -> str:
    """Compose the final system-message string via ``PromptProvider``.

    The provider's ``get_prompt`` encapsulates Langfuse-fetch + file-fallback,
    so callers do not need to pass a separate fallback string.
    """
    slots = {
        "security_preamble_section": render_security_preamble_section(
            fragments, canary_token
        ),
        "custom_instructions_section": render_custom_instructions_section(
            fragments, custom_instructions
        ),
        "user_memory_section": render_user_memory_section(fragments, user_memory_index),
        "knowledge_sphere_section": render_knowledge_sphere_section(
            fragments, ks_index
        ),
        "skills_section": render_skills_section(fragments, skills_index),
        "user_installed_mcp_section": render_user_installed_mcp_section(
            fragments, user_installed_mcp_tools or []
        ),
    }
    if prompt_provider is None:
        return ""
    return prompt_provider.get_prompt("system", **slots)


# ---------------- Trust boundary wrappers (composition-only) -----------------


def wrap_user_message(fragments: PromptFragmentsConfig, text: str) -> str:
    return fragments.wrap("user_message", text)


def wrap_tool_output(fragments: PromptFragmentsConfig, text: str) -> str:
    return fragments.wrap("tool_output", text)


def compose_for_llm(
    messages: list[BaseMessage], fragments: PromptFragmentsConfig
) -> list[BaseMessage]:
    """Return a NEW list with HumanMessage / ToolMessage wrapped for LLM composition.

    The original list and its elements are not mutated. ``id`` is preserved so
    ``add_messages`` reducer keeps its identity guarantees.
    """
    result: list[BaseMessage] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            text = m.content if isinstance(m.content, str) else str(m.content)
            result.append(
                HumanMessage(
                    content=wrap_user_message(fragments, text),
                    id=m.id,
                    additional_kwargs=dict(m.additional_kwargs),
                )
            )
        elif isinstance(m, ToolMessage):
            text = m.content if isinstance(m.content, str) else str(m.content)
            result.append(
                ToolMessage(
                    content=wrap_tool_output(fragments, text),
                    id=m.id,
                    tool_call_id=m.tool_call_id,
                    name=m.name,
                    additional_kwargs=dict(m.additional_kwargs),
                )
            )
        else:
            result.append(m)
    return result
