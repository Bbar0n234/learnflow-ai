from __future__ import annotations

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.agent.tools.ks_helpers import (
    build_namespace,
    fuzzy_find_and_replace,
    section_key,
)


def _ns(runtime: ToolRuntime) -> tuple[str, ...]:
    if runtime.context is None:
        raise RuntimeError("KS tools require AgentContext but none was provided")
    return build_namespace(runtime.context.project_id)


def _store(runtime: ToolRuntime):  # type: ignore[no-untyped-def]
    if runtime.store is None:
        raise RuntimeError("KS tools require a Store but none was provided")
    return runtime.store


@tool
async def get_section(section_id: str, runtime: ToolRuntime) -> str:
    """Get full content of a Knowledge Sphere section."""
    store = _store(runtime)
    item = await store.aget(_ns(runtime), section_key(section_id))
    if item is None:
        return f"Error: section '{section_id}' not found."
    return item.value["content"]


@tool
async def create_section(
    section_id: str,
    description: str,
    content: str,
    runtime: ToolRuntime,
) -> str:
    """Create a new Knowledge Sphere section."""
    store = _store(runtime)
    ns = _ns(runtime)
    key = section_key(section_id)
    existing = await store.aget(ns, key)
    if existing is not None:
        return f"Error: section '{section_id}' already exists. Use update_section."
    await store.aput(ns, key, {"description": description, "content": content})
    return f"Created section '{section_id}'."


@tool
async def update_section(
    section_id: str,
    content: str,
    target: str = "",
    description: str = "",
    *,
    runtime: ToolRuntime,
) -> str:
    """Update an existing Knowledge Sphere section.

    Patch mode (target provided): fuzzy find target text within section, replace with content.
    Overwrite mode (no target): replace entire section content.
    Optionally update description.
    """
    store = _store(runtime)
    ns = _ns(runtime)
    key = section_key(section_id)
    item = await store.aget(ns, key)
    if item is None:
        return f"Error: section '{section_id}' not found. Use create_section."

    value = dict(item.value)

    if target:
        new_content, success, _found, _sim = fuzzy_find_and_replace(
            value["content"], target, content
        )
        if not success:
            preview = value["content"][:200]
            return (
                f"Error: target text not found in section '{section_id}'. "
                f"Current content starts with: {preview}"
            )
        value["content"] = new_content
    else:
        value["content"] = content

    if description:
        value["description"] = description

    await store.aput(ns, key, value)
    return f"Updated section '{section_id}'."


@tool
async def delete_section(section_id: str, runtime: ToolRuntime) -> str:
    """Delete a Knowledge Sphere section."""
    store = _store(runtime)
    ns = _ns(runtime)
    key = section_key(section_id)
    item = await store.aget(ns, key)
    if item is None:
        return f"Error: section '{section_id}' not found."
    await store.adelete(ns, key)
    return f"Deleted section '{section_id}'."
