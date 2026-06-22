"""Behavior tests for the Knowledge Sphere agent tools (S6).

The tools read/write project memory through ``runtime.store`` scoped by
``runtime.context.project_id``. We drive them over a real in-memory LangGraph
store with a constructed ``ToolRuntime`` (the tool's injected collaborators),
asserting the returned message and the resulting store state. The ``ToolRuntime``
is built directly; the directly-injected ``runtime`` arg is passed to the tool's
``.coroutine`` (it is excluded from the public tool schema by design).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest
from app.agent.graph import AgentContext
from app.agent.tools.knowledge_sphere import (
    create_section,
    delete_section,
    get_section,
    update_section,
)
from app.agent.tools.ks_helpers import build_namespace, section_key
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

pytestmark = pytest.mark.unit

_PROJECT_ID = "11111111-1111-1111-1111-111111111111"

_ToolCoro = Callable[..., Awaitable[str]]


def _coro(tool: object) -> _ToolCoro:
    """Expose the tool's underlying async implementation.

    ``@tool`` returns a ``StructuredTool`` whose ``.coroutine`` is the raw async
    function; the directly-injected ``runtime`` arg is excluded from the public
    tool schema, so tests drive the coroutine directly rather than ``.ainvoke``.
    """
    return cast(_ToolCoro, cast(StructuredTool, tool).coroutine)


_create = _coro(create_section)
_get = _coro(get_section)
_update = _coro(update_section)
_delete = _coro(delete_section)


def _runtime(
    store: BaseStore | None, *, with_context: bool = True
) -> ToolRuntime[AgentContext | None, dict[str, Any]]:
    context = (
        AgentContext(project_id=_PROJECT_ID, user_id="user-1") if with_context else None
    )
    # state/stream_writer are unused by the KS tools; pass benign reals so the real
    # ToolRuntime constructs without None-typed fields.
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=store,
    )


async def _section(store: BaseStore, section_id: str) -> dict[str, Any] | None:
    item = await store.aget(build_namespace(_PROJECT_ID), section_key(section_id))
    return None if item is None else item.value


async def _require_section(store: BaseStore, section_id: str) -> dict[str, Any]:
    value = await _section(store, section_id)
    assert value is not None
    return value


@pytest.fixture
def store() -> BaseStore:
    return InMemoryStore()


# --- create_section ---------------------------------------------------------


async def test_create_section_writes_to_store(store: BaseStore) -> None:
    runtime = _runtime(store)

    result = await _create(
        section_id="goals", description="aims", content="ship it", runtime=runtime
    )

    assert "Created section 'goals'" in result
    stored = await _section(store, "goals")
    assert stored == {"description": "aims", "content": "ship it"}


async def test_create_section_duplicate_returns_error_and_preserves(
    store: BaseStore,
) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals", description="aims", content="original", runtime=runtime
    )

    result = await _create(
        section_id="goals", description="x", content="overwrite", runtime=runtime
    )

    assert "already exists" in result
    # Original content untouched.
    assert (await _require_section(store, "goals"))["content"] == "original"


# --- get_section ------------------------------------------------------------


async def test_get_section_returns_content(store: BaseStore) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals", description="d", content="the body", runtime=runtime
    )

    result = await _get(section_id="goals", runtime=runtime)

    assert result == "the body"


async def test_get_section_missing_returns_error(store: BaseStore) -> None:
    runtime = _runtime(store)

    result = await _get(section_id="absent", runtime=runtime)

    assert "not found" in result


# --- update_section ---------------------------------------------------------


async def test_update_section_overwrite_replaces_content(store: BaseStore) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals", description="d", content="old text", runtime=runtime
    )

    result = await _update(
        section_id="goals", content="new text", runtime=runtime
    )

    assert "Updated section 'goals'" in result
    assert (await _require_section(store, "goals"))["content"] == "new text"


async def test_update_section_patch_mode_replaces_target(store: BaseStore) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals",
        description="d",
        content="the quick brown fox jumps",
        runtime=runtime,
    )

    result = await _update(
        section_id="goals",
        content="lazy dog",
        target="the quick brown fox",
        runtime=runtime,
    )

    assert "Updated section 'goals'" in result
    assert (await _require_section(store, "goals"))["content"] == "lazy dog jumps"


async def test_update_section_patch_conflict_returns_error_and_preserves(
    store: BaseStore,
) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals",
        description="d",
        content="some real content",
        runtime=runtime,
    )

    result = await _update(
        section_id="goals",
        content="X",
        target="totally absent target text",
        runtime=runtime,
    )

    assert "target text not found" in result
    # Patch failed -> content unchanged.
    assert (await _require_section(store, "goals"))["content"] == "some real content"


async def test_update_section_updates_description(store: BaseStore) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals", description="old desc", content="body", runtime=runtime
    )

    await _update(
        section_id="goals", content="body2", description="new desc", runtime=runtime
    )

    assert (await _require_section(store, "goals"))["description"] == "new desc"


async def test_update_section_missing_returns_error(store: BaseStore) -> None:
    runtime = _runtime(store)

    result = await _update(
        section_id="absent", content="x", runtime=runtime
    )

    assert "not found" in result


# --- delete_section ---------------------------------------------------------


async def test_delete_section_removes_from_store(store: BaseStore) -> None:
    runtime = _runtime(store)
    await _create(
        section_id="goals", description="d", content="body", runtime=runtime
    )

    result = await _delete(section_id="goals", runtime=runtime)

    assert "Deleted section 'goals'" in result
    assert await _section(store, "goals") is None


async def test_delete_section_missing_returns_error(store: BaseStore) -> None:
    runtime = _runtime(store)

    result = await _delete(section_id="absent", runtime=runtime)

    assert "not found" in result


# --- runtime guards ---------------------------------------------------------


async def test_tool_without_store_raises(store: BaseStore) -> None:
    runtime = _runtime(None)

    with pytest.raises(RuntimeError, match="Store"):
        await _get(section_id="x", runtime=runtime)


async def test_tool_without_context_raises(store: BaseStore) -> None:
    runtime = _runtime(store, with_context=False)

    with pytest.raises(RuntimeError, match="AgentContext"):
        await _get(section_id="x", runtime=runtime)
