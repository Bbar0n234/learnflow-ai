"""Regenerate `backend/contracts/agent-tool-names.json` (feat-001, T1.8).

Thin CLI over `app.agent.tools.registry.build_tool_name_fixture` — the
single function that also backs the drift-gate test
(`backend/tests/agent/test_tool_names_fixture.py`). Deterministic and
network/DB-free: internal tool names come from module-level tool objects
and static factory-tool literals, built-in MCP names from
`configs/agent.yaml` (filesystem only).

The frontend (T2) reads this fixture to guard the completeness of its
tool-signature registry (design-brief § "Реестр подписей инструментов") —
run this after adding, removing, or renaming a built-in/internal tool, or
a built-in MCP server's `allowed_tools`, then commit the updated fixture.

Usage (from repo root):
    PYTHONPATH=backend uv run --package learnflow-backend python scripts/generate_tool_names_fixture.py
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agent.config import load_agent_config
from app.agent.tools.registry import build_tool_name_fixture

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "backend"
    / "contracts"
    / "agent-tool-names.json"
)


def main() -> None:
    agent_config = load_agent_config()
    records = build_tool_name_fixture(agent_config)
    _FIXTURE_PATH.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(records)} tool name records to {_FIXTURE_PATH}")


if __name__ == "__main__":
    main()
