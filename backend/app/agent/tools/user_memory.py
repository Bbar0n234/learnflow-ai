from __future__ import annotations

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime


def _store(runtime: ToolRuntime):  # type: ignore[no-untyped-def]
    if runtime.store is None:
        raise RuntimeError("User memory tools require a Store but none was provided")
    return runtime.store


def _user_id(runtime: ToolRuntime) -> str:
    if runtime.context is None:
        raise RuntimeError(
            "User memory tools require AgentContext but none was provided"
        )
    return runtime.context.user_id


@tool
async def save_user_memory(
    key: str, description: str, content: str, runtime: ToolRuntime
) -> str:
    """Save a memory about the user. Use descriptive keys like 'prefers-bullet-points'.

    Args:
        key: Unique key for this memory (lowercase, hyphens).
        description: One-line summary of what this memory captures.
        content: Full memory content.
    """
    store = _store(runtime)
    await store.aput(
        ("user", _user_id(runtime), "memory"),
        key,
        {"description": description, "content": content},
    )
    return f"Memory saved: {key}"


@tool
async def delete_user_memory(key: str, runtime: ToolRuntime) -> str:
    """Delete a user memory by key.

    Args:
        key: The key of the memory to delete.
    """
    store = _store(runtime)
    await store.adelete(("user", _user_id(runtime), "memory"), key)
    return f"Memory deleted: {key}"
