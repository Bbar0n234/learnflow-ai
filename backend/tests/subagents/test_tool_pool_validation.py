"""Fail-fast validation of subagent ``tools`` names against the built-in pool.

``app.main._validate_subagent_tool_pool`` runs at startup: an unknown tool
name in any spec is a config error (same severity as any typo in
``configs/*.yaml``) and must abort the boot, not surface lazily on the first
``run_subagent`` call. Pure function over a name->tool dict — solitary unit.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from app.agent.config import LLMConfig, SubagentsConfig, SubagentSpec
from app.main import _validate_subagent_tool_pool

pytestmark = pytest.mark.unit


class _NamedTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _config(*specs: SubagentSpec) -> SubagentsConfig:
    return SubagentsConfig(llm=LLMConfig(model="m"), registry=list(specs))


def _pool(*names: str) -> Any:
    # The validator only reads ``name in pool`` keys — duck-typed values suffice.
    return {name: _NamedTool(name) for name in names}


def test_all_names_resolving_passes() -> None:
    config = _config(
        SubagentSpec(name="r", description="d", prompt="p", tools=["search", "scrape"]),
        SubagentSpec(name="j", description="d", prompt="p", tools=[]),
    )

    # No exception -> startup would proceed.
    _validate_subagent_tool_pool(config, cast(Any, _pool("search", "scrape")))


def test_unknown_tool_name_aborts_startup() -> None:
    config = _config(
        SubagentSpec(name="r", description="d", prompt="p", tools=["search", "ghost"]),
    )

    with pytest.raises(RuntimeError) as exc_info:
        _validate_subagent_tool_pool(config, cast(Any, _pool("search")))

    # The message pins the offending spec and the unknown name.
    assert "ghost" in str(exc_info.value)
    assert "r" in str(exc_info.value)


def test_all_offending_specs_are_aggregated_in_one_error() -> None:
    config = _config(
        SubagentSpec(name="r1", description="d", prompt="p", tools=["missing_a"]),
        SubagentSpec(name="r2", description="d", prompt="p", tools=["missing_b"]),
    )

    with pytest.raises(RuntimeError) as exc_info:
        _validate_subagent_tool_pool(config, cast(Any, _pool("search")))

    # Both offenders reported at once — one boot, one full error, not first-only.
    message = str(exc_info.value)
    assert "missing_a" in message and "missing_b" in message
