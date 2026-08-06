"""Behavior tests for the agent-facing skill-context tools.

``get`` / ``save`` / ``delete_skill_context`` are LangChain tools built by
``make_skill_context_tools(skill_names)``: the factory closes over the startup
snapshot of the skill library, and each tool reaches the LangGraph store through
an injected ``ToolRuntime``. We drive the underlying coroutine with a duck-typed
runtime (real ``InMemoryStore`` + a minimal context) and assert the resulting
store state — the observable effect — plus the validation/limit guards that
return error strings rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.tools.skill_context import make_skill_context_tools
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.memory import InMemoryStore

_SKILL = "tech-article-writing"
_LIBRARY = frozenset({_SKILL, "meeting-summarizer"})


@dataclass
class _Ctx:
    user_id: str = "u-1"
    project_id: str = "p-1"


def _runtime(store: Any, context: Any) -> ToolRuntime:
    # The tools only touch ``runtime.store`` and ``runtime.context``; a duck-typed
    # namespace is a sufficient (and clean) double for the injected runtime.
    return cast(ToolRuntime, SimpleNamespace(store=store, context=context))


def _tools(skill_names: frozenset[str] = _LIBRARY) -> dict[str, StructuredTool]:
    tools: list[BaseTool] = make_skill_context_tools(skill_names)
    return {t.name: cast(StructuredTool, t) for t in tools}


async def _call(tool: StructuredTool, **kwargs: Any) -> str:
    assert tool.coroutine is not None
    return await tool.coroutine(**kwargs)


def _ns(user_id: str, skill: str) -> tuple[str, ...]:
    return ("user", user_id, "skill_context", skill)


# --- save: persistence, namespace, upsert -----------------------------------


@pytest.mark.unit
async def test_save_skill_context_persists_under_skill_namespace() -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-42"))

    result = await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="voice profile",
        content="writes in a dry, precise register",
        runtime=runtime,
    )

    assert "profile" in result
    item = await store.aget(_ns("u-42", _SKILL), "profile")
    assert item is not None
    assert item.value == {
        "description": "voice profile",
        "content": "writes in a dry, precise register",
    }


@pytest.mark.unit
async def test_save_skill_context_upsert_replaces_existing_value() -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    await store.aput(
        _ns("u-1", _SKILL), "profile", {"description": "old", "content": "old body"}
    )

    await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="new",
        content="new body",
        runtime=runtime,
    )

    item = await store.aget(_ns("u-1", _SKILL), "profile")
    assert item is not None
    assert item.value == {"description": "new", "content": "new body"}


@pytest.mark.unit
async def test_save_skill_context_isolated_by_skill_name() -> None:
    # Same key under two skills must not collide: the skill_name is part of the
    # namespace, so both documents coexist independently.
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="d1",
        content="article voice",
        runtime=runtime,
    )
    await _call(
        save,
        skill_name="meeting-summarizer",
        key="profile",
        description="d2",
        content="summary voice",
        runtime=runtime,
    )

    first = await store.aget(_ns("u-1", _SKILL), "profile")
    second = await store.aget(_ns("u-1", "meeting-summarizer"), "profile")
    assert first is not None and first.value["content"] == "article voice"
    assert second is not None and second.value["content"] == "summary voice"


@pytest.mark.unit
async def test_save_skill_context_isolated_by_user() -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]

    await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="d",
        content="mine",
        runtime=_runtime(store, _Ctx(user_id="u-1")),
    )

    assert await store.aget(_ns("u-2", _SKILL), "profile") is None


# --- save: skill-existence and name-format rejection ------------------------


@pytest.mark.unit
async def test_save_skill_context_rejects_unknown_skill() -> None:
    # A well-formed but unknown/misspelled skill name is refused so no orphan
    # namespace is created.
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        save,
        skill_name="tech-artikle-writing",  # typo: not in the library
        key="profile",
        description="d",
        content="c",
        runtime=runtime,
    )

    assert result.startswith("Error:")
    assert "not found in library" in result
    assert await store.aget(_ns("u-1", "tech-artikle-writing"), "profile") is None


@pytest.mark.unit
@pytest.mark.parametrize("bad_name", ["Tech Writing", "UPPER", "a/b", "../etc", "x.y"])
async def test_save_skill_context_rejects_invalid_skill_name(bad_name: str) -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        save,
        skill_name=bad_name,
        key="profile",
        description="d",
        content="c",
        runtime=runtime,
    )

    assert result.startswith("Error: invalid skill name")


# --- save: business limits (20 000 / 200 / <= 20 documents) -----------------


@pytest.mark.unit
async def test_save_skill_context_rejects_description_over_limit() -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="x" * 201,
        content="c",
        runtime=runtime,
    )

    assert result.startswith("Error:")
    assert "description exceeds" in result
    assert await store.aget(_ns("u-1", _SKILL), "profile") is None


@pytest.mark.unit
async def test_save_skill_context_rejects_content_over_limit() -> None:
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="d",
        content="x" * 20_001,
        runtime=runtime,
    )

    assert result.startswith("Error:")
    assert "content exceeds" in result
    assert await store.aget(_ns("u-1", _SKILL), "profile") is None


@pytest.mark.unit
async def test_save_skill_context_accepts_content_at_limit() -> None:
    # Boundary: exactly 20 000 chars is allowed (the check is strictly ``>``).
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        save,
        skill_name=_SKILL,
        key="profile",
        description="x" * 200,
        content="x" * 20_000,
        runtime=runtime,
    )

    assert not result.startswith("Error:")
    assert await store.aget(_ns("u-1", _SKILL), "profile") is not None


@pytest.mark.unit
async def test_save_skill_context_rejects_new_key_past_document_cap() -> None:
    # 20 documents already exist for the skill; a 21st *new* key is refused.
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    for i in range(20):
        await store.aput(
            _ns("u-1", _SKILL), f"doc-{i:02d}", {"description": "d", "content": "c"}
        )

    result = await _call(
        save,
        skill_name=_SKILL,
        key="doc-new",
        description="d",
        content="c",
        runtime=runtime,
    )

    assert result.startswith("Error:")
    assert "limit reached" in result
    assert await store.aget(_ns("u-1", _SKILL), "doc-new") is None


@pytest.mark.unit
async def test_save_skill_context_upsert_at_cap_is_allowed() -> None:
    # At the 20-document cap, overwriting an *existing* key is not blocked — the
    # count check only gates creation of a new key.
    store = InMemoryStore()
    save = _tools()["save_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    for i in range(20):
        await store.aput(
            _ns("u-1", _SKILL), f"doc-{i:02d}", {"description": "d", "content": "c"}
        )

    result = await _call(
        save,
        skill_name=_SKILL,
        key="doc-05",
        description="updated",
        content="updated body",
        runtime=runtime,
    )

    assert not result.startswith("Error:")
    item = await store.aget(_ns("u-1", _SKILL), "doc-05")
    assert item is not None and item.value["content"] == "updated body"


# --- get ---------------------------------------------------------------------


@pytest.mark.unit
async def test_get_skill_context_returns_full_content() -> None:
    store = InMemoryStore()
    get = _tools()["get_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    await store.aput(
        _ns("u-1", _SKILL),
        "profile",
        {"description": "voice", "content": "the full document body"},
    )

    result = await _call(get, skill_name=_SKILL, key="profile", runtime=runtime)

    assert result == "the full document body"


@pytest.mark.unit
async def test_get_skill_context_missing_returns_error_string() -> None:
    store = InMemoryStore()
    get = _tools()["get_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(get, skill_name=_SKILL, key="absent", runtime=runtime)

    assert result.startswith("Error:")
    assert "not found" in result


@pytest.mark.unit
async def test_get_skill_context_reads_skill_absent_from_library() -> None:
    # Storage is decoupled from library presence: a document saved for a skill
    # that is not in the registry is still readable (data outlives the skill).
    store = InMemoryStore()
    get = _tools(skill_names=frozenset())["get_skill_context"]  # empty library
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    await store.aput(
        _ns("u-1", "removed-skill"),
        "profile",
        {"description": "d", "content": "still reachable"},
    )

    result = await _call(
        get, skill_name="removed-skill", key="profile", runtime=runtime
    )

    assert result == "still reachable"


# --- delete ------------------------------------------------------------------


@pytest.mark.unit
async def test_delete_skill_context_removes_document() -> None:
    store = InMemoryStore()
    delete = _tools()["delete_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))
    await store.aput(_ns("u-1", _SKILL), "profile", {"content": "c"})

    result = await _call(delete, skill_name=_SKILL, key="profile", runtime=runtime)

    assert "profile" in result
    assert await store.aget(_ns("u-1", _SKILL), "profile") is None


@pytest.mark.unit
async def test_delete_skill_context_absent_is_idempotent() -> None:
    # Deleting a missing document does not raise and does not create anything —
    # idempotent, mirroring ``delete_user_memory``.
    store = InMemoryStore()
    delete = _tools()["delete_skill_context"]
    runtime = _runtime(store, _Ctx(user_id="u-1"))

    result = await _call(
        delete, skill_name=_SKILL, key="never-existed", runtime=runtime
    )

    assert not result.startswith("Error:")
    assert await store.aget(_ns("u-1", _SKILL), "never-existed") is None


# --- fail-fast when runtime pieces are missing ------------------------------


@pytest.mark.unit
async def test_save_skill_context_without_store_raises() -> None:
    save = _tools()["save_skill_context"]
    runtime = _runtime(None, _Ctx())

    with pytest.raises(RuntimeError):
        await _call(
            save,
            skill_name=_SKILL,
            key="profile",
            description="d",
            content="c",
            runtime=runtime,
        )


@pytest.mark.unit
async def test_save_skill_context_without_context_raises() -> None:
    save = _tools()["save_skill_context"]
    runtime = _runtime(InMemoryStore(), None)

    with pytest.raises(RuntimeError):
        await _call(
            save,
            skill_name=_SKILL,
            key="profile",
            description="d",
            content="c",
            runtime=runtime,
        )
