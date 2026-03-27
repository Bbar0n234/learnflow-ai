# CLAUDE.md

## Project Context

LearnFlowAI — AI-powered learning platform. Core stack: LangGraph agent, FastAPI backend, React/TypeScript frontend, PostgreSQL.

This project follows AIDD (AI-Driven Development): the developer acts as architect defining contracts and architecture; the LLM agent implements based on prepared documentation context. All docs live in `doc/` — read them before making assumptions.

## Documentation

Start from [doc/index.md](doc/index.md). Key entry points by concern:

```
doc/
├── idea.md              # Problem, ICP, JTBD, product boundaries
├── vision.md            # System architecture, stack, MVP criteria
├── product/             # Use cases, roadmap, versioned scope
├── tech/
│   ├── conventions.md   # Git flow, naming, code quality setup
│   └── adr/             # Architecture Decision Records
├── security/            # Threat model
└── tasks/               # Task lists and iterations
```

## Key Commands

Use Makefile targets — not raw shell commands.

| Target | Purpose |
|--------|---------|
| `make check` | All backend checks: ruff + mypy (CI gate) |
| `make lint` / `make format` | Ruff linter / formatter |
| `make type-check` | mypy |
| `make lint-fe` / `make format-fe` | ESLint / Prettier |
| `make test` | pytest |
| `make dev` / `make dev-fe` | Backend / frontend dev server |
| `make docker-up` / `make docker-up-db` | Full stack / DB only |
| `make migrate` | Alembic upgrade head |
| `make migration msg="..."` | Create new Alembic migration |

## Makefile Conventions

Makefile is the canonical interface to the project. Prefer `make <target>` over typing raw commands.

If a target is missing or inconvenient — improve the Makefile rather than running raw commands repeatedly. Obvious fixes (typos, wrong flags) can be applied directly. Non-obvious changes (new targets, workflow modifications) require architect approval.

One-off commands that won't be reused are fine to run directly.

## Code Quality Tools

Linters and formatters are the project's quality gate — work with them, not around them.

When a check fails:
- **Understand the root cause** — determine whether it's a genuine code issue or a tooling false positive.
- **Genuine issue** — fix in code.
- **False positive or missing rule** — discuss with the architect to decide whether to adjust the rule configuration.
- Never add blind suppressions (`# noqa`, `# type: ignore`) without clear justification. Suppressing real issues defeats the purpose of the tooling.

Rule changes (enabling, disabling, configuring) always go through the architect.

## Tool & Library Freshness

Do not rely on training data for fast-moving tools. Verify against these sources (in priority order):

1. **Installed packages** — Python inspect, docstrings, signatures
2. **Skills** — langgraph-patterns, uv-package-manager, etc.
3. **MCP** — docs-langchain for up-to-date LangGraph docs
4. **firecrawl** — official documentation, PyPI, GitHub

This project uses **raw LangGraph** (not LangChain wrappers). Always verify LangGraph API through the sources above.

## Skills

Use installed skills when the task matches their domain. Skills carry up-to-date, specialized knowledge beyond training data.

| Skill | When to use |
|-------|-------------|
| `aidd-methodology` | Documentation structure, tasklists, workflow, ADRs |
| `firecrawl` | Web/docs fetching, research, URL reading |
| `langfuse` | Observability, tracing, Langfuse API and docs |
| `langgraph-patterns` | LangGraph API, StateGraph, Command, HITL, streaming |
| `prompt-engineering` | Writing or reviewing system prompts for LLM |
| `schema-guided-reasoning` | Structured output, Pydantic models, JSON schema |
| `uv-package-manager` | Dependencies, pyproject.toml, workspace, venv |

When uncertain whether a skill covers your current task — check available skills before proceeding.

## Logging Conventions

Backend: `structlog.get_logger()`, keyword-args style: `logger.info("event", key=value)`. Never `logging.getLogger(__name__)`.

Frontend: `import { logger } from "@/shared/lib/logger"` instead of `console.*`.

Level semantics, style, anti-patterns — see [conventions.md](doc/tech/conventions.md#logging-conventions).

## Sandbox & Network

Sandbox isolates network per bash command (`--unshare-net`). Commands inside sandbox cannot connect to localhost services (Docker ports, dev servers, databases). This is expected — not a Docker or networking issue.

Use Makefile targets for anything that needs network access to local services — they run outside sandbox via `excludedCommands`. For one-off diagnostics (psql, curl), sandbox escape hatch will trigger automatically.

## Agent Boundaries

The agent does not make architectural decisions independently. Architecture, new components, interfaces, technology choices — only after explicit approval from the architect.

When a decision obviously follows from existing documentation — proceed. When there is any doubt — ask first. An unnecessary question is cheap; an unauthorized architectural decision is expensive.

## Parallel Development

Multiple agents may work on different features simultaneously in separate worktrees. They have no communication channel with each other.

If you observe unexpected behavior — port already in use, services restarting on their own, files changing outside your edits — **stop and escalate to the architect**. Do not attempt to resolve infrastructure conflicts yourself. The architect coordinates between agents.
