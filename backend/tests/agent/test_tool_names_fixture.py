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
from app.agent.tools.registry import build_tool_name_fixture

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
