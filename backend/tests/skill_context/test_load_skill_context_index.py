"""Behavior tests for the skill-context index appended by ``load_skill``.

``load_skill(skill_name)`` (without ``file``) is progressive disclosure: after
the skill's SKILL.md and file footer, it appends an index of the caller's saved
context documents for that skill — only ``key: description``, never the document
bodies. We build a throwaway skills tree under ``tmp_path`` (as the loader is a
filesystem function) and drive the tool through its coroutine with a duck-typed
``ToolRuntime`` (real ``InMemoryStore`` + minimal context) to assert what the
index does and does not contain.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from app.agent.tools.skills import make_load_skill_tool
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.memory import InMemoryStore

_SKILL = "alpha-skill"
_SKILL_BODY = """---
name: alpha-skill
description: Helps with alpha things.
---

# Alpha

Do alpha work.
"""


@dataclass
class _Ctx:
    user_id: str = "u-1"
    project_id: str = "p-1"


def _runtime(store: Any, context: Any = None) -> ToolRuntime:
    return cast(ToolRuntime, SimpleNamespace(store=store, context=context or _Ctx()))


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    (root / _SKILL).mkdir(parents=True)
    (root / _SKILL / "SKILL.md").write_text(_SKILL_BODY, encoding="utf-8")
    return root


def _ns(user_id: str, skill: str) -> tuple[str, ...]:
    return ("user", user_id, "skill_context", skill)


async def _load(tool: StructuredTool, **kwargs: Any) -> str:
    assert tool.coroutine is not None
    return await tool.coroutine(**kwargs)


@pytest.mark.unit
async def test_load_skill_appends_context_index_when_documents_exist(
    skills_dir: Path,
) -> None:
    store = InMemoryStore()
    await store.aput(
        _ns("u-1", _SKILL),
        "profile",
        {"description": "voice profile", "content": "FULL_DOCUMENT_BODY"},
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(tool, skill_name=_SKILL, runtime=_runtime(store))

    # Regular output is preserved, and the index lists key + description only.
    assert "Do alpha work." in content
    assert "Skill Context:" in content
    assert "- profile: voice profile" in content


@pytest.mark.unit
async def test_load_skill_index_omits_document_content(skills_dir: Path) -> None:
    # Two-level progressive disclosure: the index never leaks the body; that is
    # fetched separately via get_skill_context.
    store = InMemoryStore()
    await store.aput(
        _ns("u-1", _SKILL),
        "profile",
        {"description": "voice profile", "content": "SECRET_DOCUMENT_BODY"},
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(tool, skill_name=_SKILL, runtime=_runtime(store))

    assert "SECRET_DOCUMENT_BODY" not in content


@pytest.mark.unit
async def test_load_skill_empty_namespace_leaves_output_unchanged(
    skills_dir: Path,
) -> None:
    # An empty namespace must not append an index section at all: the output is
    # byte-identical to invoking without a runtime.
    store = InMemoryStore()
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    with_empty = await _load(tool, skill_name=_SKILL, runtime=_runtime(store))
    without_runtime = await tool.ainvoke({"skill_name": _SKILL})

    assert with_empty == without_runtime
    assert "Skill Context:" not in with_empty


@pytest.mark.unit
async def test_load_skill_without_runtime_appends_no_index(skills_dir: Path) -> None:
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await tool.ainvoke({"skill_name": _SKILL})

    assert "Do alpha work." in content
    assert "Skill Context:" not in content


@pytest.mark.unit
async def test_load_skill_index_scoped_to_loaded_skill_only(skills_dir: Path) -> None:
    # Documents saved under a different skill must not surface when loading this
    # one — the search is namespaced to the loaded skill_name.
    store = InMemoryStore()
    await store.aput(
        _ns("u-1", "other-skill"),
        "profile",
        {"description": "other voice", "content": "x"},
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(tool, skill_name=_SKILL, runtime=_runtime(store))

    assert "Skill Context:" not in content
    assert "other voice" not in content


@pytest.mark.unit
async def test_load_skill_index_isolated_per_user(skills_dir: Path) -> None:
    # A document owned by another user is not disclosed to this caller.
    store = InMemoryStore()
    await store.aput(
        _ns("u-2", _SKILL),
        "profile",
        {"description": "their voice", "content": "x"},
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(
        tool, skill_name=_SKILL, runtime=_runtime(store, _Ctx(user_id="u-1"))
    )

    assert "Skill Context:" not in content
    assert "their voice" not in content


@pytest.mark.unit
async def test_load_skill_file_form_appends_no_index(skills_dir: Path) -> None:
    # The index is only for the skill-load form; loading a specific file returns
    # just that file's content, never a context index.
    (skills_dir / _SKILL / "module.md").write_text("module body", encoding="utf-8")
    store = InMemoryStore()
    await store.aput(
        _ns("u-1", _SKILL), "profile", {"description": "voice", "content": "x"}
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(
        tool, skill_name=_SKILL, file="module.md", runtime=_runtime(store)
    )

    assert "module body" in content
    assert "Skill Context:" not in content


@pytest.mark.unit
async def test_load_skill_unknown_skill_appends_no_index(skills_dir: Path) -> None:
    # An error result (unknown skill) is returned untouched — no index is glued
    # onto an error string.
    store = InMemoryStore()
    await store.aput(
        _ns("u-1", "ghost"), "profile", {"description": "voice", "content": "x"}
    )
    tool = cast(StructuredTool, make_load_skill_tool(skills_dir))

    content = await _load(tool, skill_name="ghost", runtime=_runtime(store))

    assert content.startswith("Error:")
    assert "Skill Context:" not in content
