"""Corpus collection: tool registry (PairedDetector) + fragment corpus.

Pure collection over LangChain ``BaseTool`` objects — real tools built with the
``@tool`` decorator, no mocks needed (they are in-process pure data).
"""

from __future__ import annotations

import pytest
from app.agent.security.corpus import collect_fragment_corpus, collect_tool_registry
from langchain_core.tools import tool


@tool
def save_user_memory(content: str, scope: str) -> str:
    """Persist a user memory entry."""
    return content


@tool
def load_skill(skill_name: str) -> str:
    """Load a skill by name."""
    return skill_name


@pytest.mark.unit
def test_collect_tool_registry_maps_name_to_param_names() -> None:
    registry = collect_tool_registry([save_user_memory, load_skill])

    assert registry == {
        "save_user_memory": ["content", "scope"],
        "load_skill": ["skill_name"],
    }


@pytest.mark.unit
def test_collect_tool_registry_skips_non_tools() -> None:
    registry = collect_tool_registry([save_user_memory, "not a tool", 42])

    assert set(registry) == {"save_user_memory"}


@pytest.mark.unit
def test_collect_fragment_corpus_includes_prompts_and_tool_descriptions() -> None:
    corpus = collect_fragment_corpus(
        system_prompt="hardening preamble text",
        guard_classifier_prompt="security classifier instructions",
        internal_tools=[save_user_memory, load_skill],
    )

    assert "hardening preamble text" in corpus
    assert "security classifier instructions" in corpus
    # Tool descriptions are part of the PROTECTED surface.
    assert "Persist a user memory entry." in corpus
    assert "Load a skill by name." in corpus


@pytest.mark.unit
def test_collect_fragment_corpus_omits_empty_sources() -> None:
    corpus = collect_fragment_corpus(
        system_prompt="",
        guard_classifier_prompt="",
        internal_tools=[],
    )

    assert corpus == []


@pytest.mark.unit
def test_collect_fragment_corpus_skips_non_tool_entries() -> None:
    corpus = collect_fragment_corpus(
        system_prompt="prompt",
        guard_classifier_prompt="",
        internal_tools=["not a tool"],
    )

    assert corpus == ["prompt"]
