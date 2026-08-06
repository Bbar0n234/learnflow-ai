<picture>
  <source media="(prefers-color-scheme: dark)" srcset="doc/assets/readme/banner-dark.png">
  <img src="doc/assets/readme/banner-light.png" alt="LearnFlowAI — an AI workspace that turns your expertise into structured talks, articles, and courses">
</picture>

<p align="center">
  <a href="#what-is-learnflowai">About</a> ·
  <a href="#screenshots">Screenshots</a> ·
  <a href="#features">Features</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#documentation">Docs</a>
</p>

## What is LearnFlowAI

Tech speakers, educators, and course authors all share the same routine: you have deep expertise and a head full of context, but turning it into a structured talk, article, or course eats hours. Generic LLM chats don't really help — context evaporates between sessions, every new chat starts from zero, and you spend the first ten minutes re-explaining what you already told the model last week.

LearnFlowAI is an open-source AI workspace built around a different core idea: **the project as a sphere of context**. You create a project (a talk, a course, an article series) and work inside it through chats. As you work, the agent accumulates a **Knowledge Sphere** — a versioned, structured memory of the project: decisions made, terminology agreed on, materials produced. The next session picks up exactly where you left off, and the agent loads only the context relevant to the current task instead of drowning in the full history.

On top of that memory sits a **general LangGraph agent with pluggable skills** — methodology knowledge contributed by humans (how to structure a lecture, how to build a narrative arc) that the agent loads on demand. The agent produces real artifacts: outlines, summaries, slide decks — not just chat replies.

## Screenshots

<table>
  <tr>
    <td width="50%">
      <img src="doc/assets/readme/screen-welcome-light.png" alt="Welcome screen with project list">
    </td>
    <td width="50%">
      <img src="doc/assets/readme/screen-chat-dark.png" alt="Chat with an agent writing to the Knowledge Sphere (dark theme)">
    </td>
  </tr>
  <tr>
    <td align="center"><em>Projects workspace</em></td>
    <td align="center"><em>Agent writes to the Knowledge Sphere right from the chat</em></td>
  </tr>
</table>

<p align="center">
  <img src="doc/assets/readme/screen-sphere-light.png" width="85%" alt="Knowledge Sphere: versioned project memory with chronicle and version history">
  <br><em>Knowledge Sphere — versioned project memory with chronicle and version history</em>
</p>

## Features

- **Knowledge Sphere** — versioned project memory. Every agent write is a reviewed patch with a diff, a version bump, and one-click rollback. Progressive disclosure keeps the agent's context lean.
- **General agent + skills** — a single LangGraph agent extended through pluggable skills and tools instead of hardcoded pipelines. Sub-agents isolate heavy work with their own context.
- **Live agent activity** — the UI streams what the agent is actually doing over SSE: tool calls, sub-agent runs, sphere writes — a real-time activity feed, not a spinner.
- **Artifacts** — structured outputs (summaries, study plans, slide decks) live alongside chats inside the project, not buried in the transcript.
- **Security built in** — prompt-injection defense pipeline plus a dedicated SIEM service that consumes security events through Redis Streams, correlates them, and raises alerts.
- **Observability** — full Langfuse tracing with per-request cost accounting and prompt management (dev/prod prompt lifecycles).

## Architecture

```mermaid
graph TD
    Frontend["React SPA<br/>frontend/"]

    subgraph Backend["Main Backend — FastAPI · backend/"]
        API["API Layer"]
        Runtime["Agent Runtime — LangGraph<br/>general agent · skills · sub-agents"]
        SecPipe["Security Pipeline"]
    end

    subgraph SIEM["SIEM Service — FastAPI · services/siem-service/"]
        Correlation["Correlation Engine + REST API"]
    end

    MainDB[("PostgreSQL<br/>checkpoints · sphere · chats")]
    SiemDB[("PostgreSQL<br/>events · alerts")]
    Redis[("Redis Streams")]
    External["LLM APIs · MCP · Langfuse"]

    Frontend -->|HTTP + SSE| API
    API --> Runtime
    API --> MainDB
    Runtime --> MainDB
    Runtime --> External
    SecPipe --> Redis
    Redis --> SIEM
    Correlation --> SiemDB
```

**Stack:** Python 3.12 · FastAPI · LangGraph (plain, no LangChain wrappers) · PostgreSQL · Redis · React + TypeScript (Feature-Sliced Design) · uv workspace monorepo · Langfuse.

The project is developed with **AIDD (AI-Driven Development)**: the architect defines contracts and architecture in `doc/`, and LLM agents implement against that documented context. The full decision trail lives in [ADRs](doc/tech/adr/) and iteration artifacts — the repository doubles as a working example of the methodology.

## Quick Start

### Prerequisites

- Docker and Docker Compose v2
- For local dev: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js 20+

### Docker (full stack)

```bash
git clone https://github.com/Bbar0n234/learnflow-ai.git
cd learnflow-ai

cp .env.example .env
# Edit .env — set your LLM API keys

make docker-build && make docker-up
# App available at http://localhost:8000
```

### Local dev (DB in Docker, app locally)

```bash
uv sync
cd frontend && npm install && cd ..

cp .env.local.example .env.local

make docker-up-db   # PostgreSQL + Redis
make dev            # backend at http://localhost:8000
make dev-fe         # frontend at http://localhost:5173
```

### Useful commands

| Command | Description |
|---------|-------------|
| `make check` / `make check-fe` | All backend / frontend checks (CI gate) |
| `make test` | Run pytest |
| `make migrate` | Apply DB migrations |
| `make docker-logs` | Tail app container logs |

The full command list is in the [Makefile](Makefile).

## Documentation

All project documentation lives in [`doc/`](doc/index.md) (in Russian):

- [idea.md](doc/idea.md) — problem, ICP, JTBD, product boundaries
- [vision.md](doc/vision.md) — system architecture and MVP criteria
- [doc/product/](doc/product/) — use cases, roadmap, versioned scope
- [doc/tech/](doc/tech/) — component docs, conventions, [ADRs](doc/tech/adr/)
- [doc/tasks/](doc/tasks/) — task lists and iteration artifacts

## License

MIT
