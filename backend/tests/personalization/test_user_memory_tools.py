"""Behavior tests for the agent-facing user-memory tools.

``save_user_memory`` / ``delete_user_memory`` are LangChain tools that reach the
LangGraph store through an injected ``ToolRuntime``. We drive the underlying
coroutine with a duck-typed runtime (real ``InMemoryStore`` + a minimal context)
and assert the resulting store state — the observable effect — plus the
fail-fast guards when runtime pieces are missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.tools.user_memory import delete_user_memory, save_user_memory
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.memory import InMemoryStore

_save = cast(StructuredTool, save_user_memory)
_delete = cast(StructuredTool, delete_user_memory)


@dataclass
class _Ctx:
    user_id: str = "u-1"
    project_id: str = "p-1"


def _runtime(store: Any, context: Any) -> ToolRuntime:
    # The tools only touch ``runtime.store`` and ``runtime.context``; a duck-typed
    # namespace is a sufficient (and clean) double for the injected runtime.
    return cast(ToolRuntime, SimpleNamespace(store=store, context=context))


async def _call(tool: StructuredTool, **kwargs: Any) -> str:
    assert tool.coroutine is not None
    return await tool.coroutine(**kwargs)


@pytest.mark.unit
async def test_save_user_memory_persists_under_user_namespace() -> None:
    store = InMemoryStore()
    runtime = _runtime(store, _Ctx(user_id="u-42"))

    result = await _call(
        _save,
        key="prefers-bullets",
        description="formatting preference",
        content="use bullet points",
        runtime=runtime,
    )

    assert "prefers-bullets" in result
    item = await store.aget(("user", "u-42", "memory"), "prefers-bullets")
    assert item is not None
    assert item.value == {
        "description": "formatting preference",
        "content": "use bullet points",
    }


@pytest.mark.unit
async def test_delete_user_memory_removes_saved_item() -> None:
    store = InMemoryStore()
    runtime = _runtime(store, _Ctx(user_id="u-42"))
    await store.aput(("user", "u-42", "memory"), "k", {"content": "c"})

    result = await _call(_delete, key="k", runtime=runtime)

    assert "k" in result
    assert await store.aget(("user", "u-42", "memory"), "k") is None


@pytest.mark.unit
async def test_save_user_memory_without_store_raises() -> None:
    runtime = _runtime(None, _Ctx())

    with pytest.raises(RuntimeError):
        await _call(_save, key="k", description="d", content="c", runtime=runtime)


@pytest.mark.unit
async def test_save_user_memory_without_context_raises() -> None:
    runtime = _runtime(InMemoryStore(), None)

    with pytest.raises(RuntimeError):
        await _call(_save, key="k", description="d", content="c", runtime=runtime)
