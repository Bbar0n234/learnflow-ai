"""Unit: `backend/contracts/agent-tool-names.json` drift gate (T1.8).

No network, no DB — pure config-loading + object introspection, same class
as `test_pricing_consistency.py`. The committed fixture is a contract the
frontend (T2) reads to guard its tool-signature registry (design-brief §
"Реестр подписей инструментов"); if someone adds/renames/removes a
built-in/internal tool or a built-in MCP server's `allowed_tools` without
regenerating the fixture, this test goes red and names the regeneration
command.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.agent.config import load_agent_config
from app.agent.tools.registry import (
    build_tool_name_fixture,
    builtin_mcp_tool_names,
    internal_tool_names,
)

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "agent-tool-names.json"
)

_REGENERATE_COMMAND = (
    "PYTHONPATH=backend uv run --package learnflow-backend python "
    "scripts/generate_tool_names_fixture.py"
)


@pytest.mark.unit
def test_fixture_matches_generated_output() -> None:
    committed = json.loads(_FIXTURE_PATH.read_text())
    generated = build_tool_name_fixture(load_agent_config())

    assert committed == generated, (
        "backend/contracts/agent-tool-names.json is stale — regenerate with:\n"
        f"    {_REGENERATE_COMMAND}"
    )


@pytest.mark.unit
def test_fixture_has_the_shape_the_frontend_registry_test_reads() -> None:
    # Cross-track contract: T2's registry-completeness test reads this file
    # directly, so its *shape* — sorted records of ``name`` + ``origin`` from a
    # closed set — is as load-bearing as its contents, and neither side can
    # change it unilaterally without going red here.
    committed = json.loads(_FIXTURE_PATH.read_text())

    assert isinstance(committed, list) and committed
    assert all(record.keys() == {"name", "origin"} for record in committed)
    assert {record["origin"] for record in committed} <= {"internal", "builtin_mcp"}
    names = [record["name"] for record in committed]
    assert names == sorted(names)
    assert len(names) == len(set(names))


@pytest.mark.unit
def test_fixture_covers_the_tools_the_agent_is_actually_built_with() -> None:
    # The point of generating the fixture from the registry is that a new tool
    # cannot reach the agent without a signature being demanded for it; these
    # names are the ones every deployment ships, so their absence would mean
    # the fixture drifted away from the assembly it claims to describe.
    committed = {record["name"] for record in json.loads(_FIXTURE_PATH.read_text())}

    assert {"run_subagent", "create_artifact", "generate_image"} <= committed
    assert set(internal_tool_names()) <= committed
    assert set(builtin_mcp_tool_names(load_agent_config())) <= committed
