"""Single source of truth for the agent's built-in tool set (T1.8).

`app.main`'s startup and `scripts/generate_tool_names_fixture.py` must never
maintain their own, independently-edited lists of which tools the agent can
be given — a fixture generated from a list parallel to the one `app.main`
actually assembles would silently drift from what the graph receives at
runtime (design-brief § "Реестр подписей инструментов"; plan T1.8).

- `assemble_internal_tools` is what `app.main` calls to build the real
  `internal_tools` list, bound to runtime dependencies (a DB session
  factory, `Settings`, the skill library, a `Workspace`, an optional
  `SubagentRunner`-backed `run_subagent`).
- `internal_tool_names` is what the fixture generator (and its drift-gate
  test, `backend/tests/agent/test_tool_names_fixture.py`) calls instead: it
  walks the *same* tool groups, but never touches a runtime dependency —
  `ks_tools`/`user_memory_tools` are plain module-level lists, and
  `make_skill_context_tools` needs nothing but the (here, empty) skill-name
  set it validates saves against. The factory-built tools (`load_skill`,
  `read_file`, `write_file`, `list_files`, `execute_code`, `run_command`,
  `generate_image`, `run_subagent`) are listed as literals rather than
  constructed: building real instances would require a live DB session
  factory, a validated `Settings`/`Workspace`, or a `SubagentRunner` —
  dependencies a static, network/DB-free generator must not need. Listing
  them as literals is safe because each tool's `.name` is fixed at import
  time — the `@tool` decorator defaults it to the wrapped function's
  `__name__`, never to anything passed into the factory.
- `builtin_mcp_tool_names` reads `configs/agent.yaml` (filesystem only, no
  network/DB) for every declared server's `allowed_tools`, independent of
  `enabled` — the signature registry the frontend consults must cover a
  server whenever it *can* be turned on, not only in this environment's
  current toggle state.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agent.config import AgentConfig
from app.agent.tools import ks_tools, make_skill_context_tools, user_memory_tools

# Names of the tools built by runtime-bound factories (`make_load_skill_tool`,
# `make_file_tools`, `make_execution_tools`, `make_generate_image_tool`,
# `make_run_subagent_tool`). See module docstring for why these are literals,
# not constructed instances.
_FACTORY_BUILT_TOOL_NAMES: tuple[str, ...] = (
    "load_skill",
    "read_file",
    "write_file",
    "list_files",
    "execute_code",
    "run_command",
    "generate_image",
    "run_subagent",
)


def internal_tool_names() -> list[str]:
    """Names of every internal tool the agent can be given, in any environment.

    Includes `run_subagent` unconditionally: `configs/agent.yaml`'s
    `subagents` section is optional per-environment, same reasoning as
    `builtin_mcp_tool_names` not filtering by `enabled` — a signature is
    needed wherever the tool *can* appear, not only where this environment
    happens to enable it.
    """
    names = [t.name for t in ks_tools]
    names += [t.name for t in user_memory_tools]
    names += [t.name for t in make_skill_context_tools(frozenset())]
    names += list(_FACTORY_BUILT_TOOL_NAMES)
    return names


def assemble_internal_tools(
    *,
    skill_context_tools: list[BaseTool],
    file_tools: list[BaseTool],
    execution_tools: list[BaseTool],
    load_skill: BaseTool,
    generate_image: BaseTool,
    run_subagent: BaseTool | None = None,
) -> list[BaseTool]:
    """Assemble the `internal_tools` list `app.main` hands to the graph.

    The one place composing this grouping — `internal_tool_names` above
    walks the same groups (`ks_tools`, `user_memory_tools`, skill-context,
    file tools, execution tools, plus the remaining factory-built tools), so
    the fixture can never diverge from what `app.main` actually assembles.
    """
    tools: list[BaseTool] = [
        *ks_tools,
        *user_memory_tools,
        *skill_context_tools,
        *file_tools,
        *execution_tools,
        load_skill,
        generate_image,
    ]
    if run_subagent is not None:
        tools.append(run_subagent)
    return tools


def builtin_mcp_tool_names(agent_config: AgentConfig) -> list[str]:
    """Built-in MCP tool names declared in `configs/agent.yaml`, any `enabled`.

    `enabled` toggles per-environment (e.g. a missing API key disables a
    server) — the fixture must cover the signature whenever the server is
    merely *declared*, since it can be turned on elsewhere.
    """
    names: list[str] = []
    for server_config in agent_config.mcp_servers.values():
        names.extend(server_config.allowed_tools)
    return names


def build_tool_name_fixture(agent_config: AgentConfig) -> list[dict[str, str]]:
    """Build the sorted `{name, origin}` records for `agent-tool-names.json`.

    `origin` is `"internal"` or `"builtin_mcp"` — user-installed MCP tools
    are resolved at runtime and deliberately excluded (design-brief §
    "Реестр подписей инструментов": the frontend renders those with their
    raw name plus a source annotation instead of a registry lookup).
    """
    records = [{"name": name, "origin": "internal"} for name in internal_tool_names()]
    records += [
        {"name": name, "origin": "builtin_mcp"}
        for name in builtin_mcp_tool_names(agent_config)
    ]
    return sorted(records, key=lambda record: record["name"])
