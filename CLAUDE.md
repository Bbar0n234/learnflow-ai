# CLAUDE.md

## Project Context

LearnFlowAI — AI-powered learning platform. Core stack: LangGraph agent, FastAPI backend, React/TypeScript frontend, PostgreSQL.

This project follows AIDD (AI-Driven Development): the developer acts as architect defining contracts and architecture; the LLM agent implements based on prepared documentation context. All docs live in `doc/` — read them before making assumptions.

## Project Structure

uv workspace monorepo — each package has its own `pyproject.toml` and dependencies. Root `pyproject.toml` is the workspace root, not a runnable package.

Python commands must run from the package directory (where the relevant `pyproject.toml` lives), not from the project root. Makefile targets handle this automatically.

## Hard Rules

These rules apply to every code change. The "why" behind each one is documented in `doc/tech/conventions.md`; here are the one-liners.

- **DB migrations**: schema changes go through `alembic revision --autogenerate` against a running DB. Hand-written migrations are accepted only for DML/data migrations or DDL outside autogenerate's reach, with a `# Manual migration: <reason>` header and architect approval. "DB is not running" is not a reason to write one by hand — start the DB.
- **Imports**: top-level only. A local import inside a function requires a `# lazy: <reason>` or `# circular: <reason>` comment. `PLC0415` is enforced by ruff.
- **Interfaces**: `typing.Protocol` by default. `abc.ABC` only when there is shared implementation in the base class.
- **Module-level state**: no module-level singletons. State lives in `app.state` (FastAPI), in closures (callbacks/processors outside request scope), or in DI for tests.
- **Env vs constants**: per-environment values, secrets, and operational knobs go to `Settings(BaseSettings)`. Business invariants stay in code. Adding an env variable means updating `Settings`, `.env.example`, `.env.local.example`, and `docker-compose.yml` together.
- **Workspace layout**: `packages/` for shared libraries (imported by other packages); `services/` (and historical `backend/`) for standalone runtimes. Dockerfile lives next to the package's `pyproject.toml`; build context is repo root.

## Documentation

When exploring the codebase for a task, start from architectural documents in `doc/tech/`, not source code. Documents describe interfaces, contracts, and flows at the right abstraction level for design decisions. Code is an implementation detail — use it to verify specifics not covered by documentation.

**Before editing code on a non-trivial task, open `doc/tech/conventions.md`.** The Hard Rules above are the short version; conventions.md is the source of truth for the rest (logging, naming, types, env workflow, migration workflow). Read the relevant section instead of guessing.

**В облачных сессиях (Claude Code on the web и аналоги)** действует отдельная merge-policy: агент доводит фичу до feature-ветки, push + PR в `develop`, merge — за архитектором локально. См. `doc/tech/conventions.md` § Cloud sessions.

When discussing architecture, visualize components, layers, and data flows so the architect can give quality feedback with the full picture in front of them. Don't wait to be asked. In chat — ASCII diagrams; when writing to documents — Mermaid.

Start from [doc/index.md](doc/index.md). Key entry points by concern:

```
doc/
├── idea.md              # Problem, ICP, JTBD, product boundaries
├── vision.md            # System architecture, stack, MVP criteria
├── product/             # Use cases, roadmap, versioned scope
├── tech/
│   ├── backend.md           # Layers, API, persistence, configuration
│   ├── frontend.md          # Screens, components, state, API integration
│   ├── auth.md              # JWT + refresh tokens, rate limiting, interceptor
│   ├── streaming.md         # SSE protocol, events, cancellation
│   ├── agent-runtime.md     # LangGraph graph, tools, skills, context, MCP
│   ├── knowledge-sphere.md  # Project memory, storage, fuzzy patch, REST API
│   ├── user-memory.md       # Custom instructions, agent memory, personalization
│   ├── prompt-management.md # Langfuse prompts, dev/prod, seed/sync
│   ├── observability.md     # Langfuse tracing, cost tracking, feedback loop
│   ├── conventions.md       # Git flow, naming, code quality, documentation
│   └── adr/                 # Architecture Decision Records
├── research/            # Technology research, deep-dives, approach analysis
├── reference/           # Reference materials: patterns, domain handbooks
├── security/            # Threat model + defense architecture (architecture.md)
└── tasks/               # Task lists and iterations
```

## Key Commands

Use Makefile targets — not raw shell commands.

| Target | Purpose |
|--------|---------|
| `make check` | All backend checks: ruff + mypy (CI gate) |
| `make check-fe` | All frontend checks: ESLint + Prettier --check (CI gate) |
| `make lint` / `make format` | Ruff linter / formatter |
| `make type-check` | mypy |
| `make lint-fe` / `make format-fe` | ESLint / Prettier |
| `make test` | pytest |
| `make dev` / `make dev-fe` | Backend / frontend dev server |
| `make docker-up` / `make docker-up-db` | Full stack / DB only |
| `make migrate` | Alembic upgrade head |
| `make migration msg="..."` | Create new Alembic migration |
| `make grant-admin USER=<name>` | Promote an existing user to admin |

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
