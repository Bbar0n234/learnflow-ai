"""Unit: pricing.yaml consistency against the active model set.

No network — pure config-loading + regex checks. Every model actually wired
into ``agent.yaml``/``security.yaml`` (main, summarization, subagents, the
whitelist, and the guard) must have exactly one matching entry in
``pricing.yaml``, so cost-attribution (Langfuse) and drift checks
(``test_pricing_external.py``) resolve unambiguously. Retention-only entries
(models dropped from the config but kept for legacy per-scope overrides) are
allowed to sit outside this active set.
"""

from __future__ import annotations

import re

import pytest
from app.agent.config import (
    AgentConfig,
    ModelDefinitionConfig,
    load_agent_config,
    load_pricing_config,
)
from app.agent.security.config import load_security_config
from app.agent.security.types import SecurityConfig


def _active_model_slugs(agent: AgentConfig, security: SecurityConfig) -> set[str]:
    """Every model slug actually referenced by the shipped configs."""
    slugs = {agent.llm.model, agent.title.model, security.llm_classifier.model}
    if agent.summarization is not None:
        slugs.add(agent.summarization.model)
    if agent.subagents is not None:
        slugs.add(agent.subagents.llm.model)
    slugs.update(m.name for m in agent.available_models)
    return slugs


@pytest.fixture
def agent_config() -> AgentConfig:
    return load_agent_config()


@pytest.fixture
def security_config() -> SecurityConfig:
    return load_security_config()


@pytest.fixture
def pricing_models() -> list[ModelDefinitionConfig]:
    return load_pricing_config().models


@pytest.mark.unit
def test_active_model_set_is_non_empty(
    agent_config: AgentConfig, security_config: SecurityConfig
) -> None:
    # Sanity guard: if this collapses to empty, every assertion below would
    # vacuously pass and the test would stop meaning anything.
    assert len(_active_model_slugs(agent_config, security_config)) >= 6


@pytest.mark.unit
def test_all_pricing_patterns_compile(
    pricing_models: list[ModelDefinitionConfig],
) -> None:
    for entry in pricing_models:
        re.compile(entry.match_pattern)  # raises re.error on malformed pattern


@pytest.mark.unit
def test_active_models_each_match_exactly_one_pricing_entry(
    agent_config: AgentConfig,
    security_config: SecurityConfig,
    pricing_models: list[ModelDefinitionConfig],
) -> None:
    active = _active_model_slugs(agent_config, security_config)
    unmatched: list[str] = []
    ambiguous: dict[str, list[str]] = {}

    for slug in sorted(active):
        matches = [
            entry.name
            for entry in pricing_models
            if re.match(entry.match_pattern, slug)
        ]
        if len(matches) == 0:
            unmatched.append(slug)
        elif len(matches) > 1:
            ambiguous[slug] = matches

    assert not unmatched, f"Active models with no pricing.yaml entry: {unmatched}"
    assert not ambiguous, f"Active models matched by >1 pricing.yaml entry: {ambiguous}"
