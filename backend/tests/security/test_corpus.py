"""Corpus collection: tool registry (PairedDetector) + fragment corpus.

Pure collection over LangChain ``BaseTool`` objects — real tools built with the
``@tool`` decorator, no mocks needed (they are in-process pure data).

The hardening preamble is now a *separate* corpus source: it lives in
``prompt_fragments.yaml``, not in the system-prompt template, so it reaches
``FragmentDetector`` only if the caller passes it. The regression at the bottom
of this file wires the real config files together and asserts it does — that is
the "silent detection weakening" the move could have introduced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.agent.config import load_prompt_fragments
from app.agent.security.corpus import collect_fragment_corpus, collect_tool_registry
from app.infra.prompt_provider import PromptProvider
from langchain_core.tools import tool
from tests.security.conftest import PREAMBLE_MARKER

_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs"


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
        security_preamble="",
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
        security_preamble="",
    )

    assert corpus == []


@pytest.mark.unit
def test_collect_fragment_corpus_skips_non_tool_entries() -> None:
    corpus = collect_fragment_corpus(
        system_prompt="prompt",
        guard_classifier_prompt="",
        internal_tools=["not a tool"],
        security_preamble="",
    )

    assert corpus == ["prompt"]


# --- the hardening preamble as its own corpus source ------------------------


@pytest.mark.unit
def test_collect_fragment_corpus_includes_the_security_preamble() -> None:
    corpus = collect_fragment_corpus(
        system_prompt="base prompt",
        guard_classifier_prompt="classifier instructions",
        internal_tools=[save_user_memory],
        security_preamble="hardening preamble text",
    )

    # Full list, so the preamble's place among the other sources is pinned too.
    assert corpus == [
        "base prompt",
        "hardening preamble text",
        "classifier instructions",
        "Persist a user memory entry.",
    ]


@pytest.mark.unit
def test_collect_fragment_corpus_omits_an_empty_security_preamble() -> None:
    # Defense off: no preamble in the config, so nothing to protect from leaking.
    corpus = collect_fragment_corpus(
        system_prompt="base prompt",
        guard_classifier_prompt="",
        internal_tools=[],
        security_preamble="",
    )

    assert corpus == ["base prompt"]


@pytest.mark.unit
def test_real_configs_keep_the_preamble_under_fragment_detection() -> None:
    """Regression: the preamble must not fall out of the PROTECTED corpus.

    Moving the ``<system_instructions>`` block from ``system.txt`` into
    ``prompt_fragments.yaml`` removed it from the raw template the corpus used
    to be built from. If the composition root ever stops passing
    ``security_preamble``, ``FragmentDetector`` silently stops catching the
    leak of the preamble while the guard still reports itself as enabled — the
    worst failure mode of this refactor. Both halves are asserted: the template
    no longer carries the text, and the corpus still does.
    """
    provider = PromptProvider(
        langfuse=None, label="test", cache_ttl=0, prompts_dir=_CONFIGS_DIR / "prompts"
    )
    system_template = provider.load_file("system")
    fragments = load_prompt_fragments()

    corpus = collect_fragment_corpus(
        system_prompt=system_template,
        guard_classifier_prompt=provider.load_file("security-classifier"),
        internal_tools=[save_user_memory],
        security_preamble=fragments.security_preamble,
    )

    assert PREAMBLE_MARKER not in system_template
    assert any(PREAMBLE_MARKER in part for part in corpus)
