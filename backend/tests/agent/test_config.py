"""Unit: agent config models + loaders.

Pure data logic: ``PromptFragmentsConfig.wrap`` (idempotent tag wrapping),
``open_close`` lookup, ``PromptsRegistry.resolve`` (config-path navigation), and
that the real ``configs/*.yaml`` load into their typed models.
"""

from __future__ import annotations

import pytest
from app.agent.config import (
    AgentConfig,
    PromptEntry,
    PromptFragmentsConfig,
    PromptsRegistry,
    load_agent_config,
    load_error_messages,
    load_prompt_fragments,
    load_prompts_registry,
)


@pytest.fixture
def fragments() -> PromptFragmentsConfig:
    return PromptFragmentsConfig(
        wrappers={"user_message": ["<um>", "</um>"], "bad": ["only-one"]}
    )


@pytest.mark.unit
def test_wrap_adds_tags_around_text(fragments: PromptFragmentsConfig) -> None:
    assert fragments.wrap("user_message", "hi") == "<um>\nhi\n</um>"


@pytest.mark.unit
def test_wrap_is_idempotent_when_already_wrapped(
    fragments: PromptFragmentsConfig,
) -> None:
    once = fragments.wrap("user_message", "hi")

    assert fragments.wrap("user_message", once) == once


@pytest.mark.unit
def test_wrap_unknown_or_malformed_key_returns_text_unchanged(
    fragments: PromptFragmentsConfig,
) -> None:
    assert fragments.wrap("missing", "hi") == "hi"
    assert fragments.wrap("bad", "hi") == "hi"


@pytest.mark.unit
def test_open_close_returns_pair_or_none(fragments: PromptFragmentsConfig) -> None:
    assert fragments.open_close("user_message") == ("<um>", "</um>")
    assert fragments.open_close("missing") is None
    assert fragments.open_close("bad") is None


def _minimal_agent_cfg() -> AgentConfig:
    return AgentConfig.model_validate(
        {"llm": {"model": "m"}, "context": {"max_tokens": 100}}
    )


@pytest.mark.unit
def test_prompts_registry_resolve_navigates_source_path() -> None:
    agent_cfg = _minimal_agent_cfg()
    registry = PromptsRegistry(
        prompts={
            "summarization": PromptEntry(
                source="agent.context", keys={"max": "max_tokens"}
            )
        }
    )

    resolved = registry.resolve("summarization", agent_cfg, security_cfg=None)

    assert resolved == {"max": 100}


@pytest.mark.unit
def test_prompts_registry_resolve_unknown_name_returns_empty() -> None:
    registry = PromptsRegistry(prompts={})

    assert registry.resolve("nope", _minimal_agent_cfg(), security_cfg=None) == {}


@pytest.mark.unit
def test_prompts_registry_resolve_missing_source_returns_empty() -> None:
    registry = PromptsRegistry(
        prompts={"x": PromptEntry(source="agent.does_not_exist", keys={"a": "b"})}
    )

    assert registry.resolve("x", _minimal_agent_cfg(), security_cfg=None) == {}


@pytest.mark.unit
def test_load_real_configs_parse_into_typed_models() -> None:
    agent = load_agent_config()
    fragments = load_prompt_fragments()
    errors = load_error_messages()
    prompts = load_prompts_registry()

    assert isinstance(agent, AgentConfig)
    assert agent.context.max_tokens > 0
    assert fragments.open_close("user_message") is not None
    assert errors.generic
    assert isinstance(prompts, PromptsRegistry)
