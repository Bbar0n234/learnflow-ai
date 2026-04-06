from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


@tool
async def save_user_memory(
    key: str, description: str, content: str, *, runtime: Any
) -> str:
    """Save a memory about the user. Use descriptive keys like 'prefers-bullet-points'.

    Args:
        key: Unique key for this memory (lowercase, hyphens).
        description: One-line summary of what this memory captures.
        content: Full memory content.
    """
    if runtime.store is None:
        return "Error: Store not available"
    user_id = runtime.context.user_id
    await runtime.store.aput(
        ("user", user_id, "memory"),
        key,
        {"description": description, "content": content},
    )
    return f"Memory saved: {key}"


@tool
async def delete_user_memory(key: str, *, runtime: Any) -> str:
    """Delete a user memory by key.

    Args:
        key: The key of the memory to delete.
    """
    if runtime.store is None:
        return "Error: Store not available"
    user_id = runtime.context.user_id
    await runtime.store.adelete(("user", user_id, "memory"), key)
    return f"Memory deleted: {key}"
