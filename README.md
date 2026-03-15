# LearnFlowAI

AI-powered tool for tech speakers and presenters to structure and prepare educational materials.

> **Status:** v2 in development (clean rewrite using AIDD methodology)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker and Docker Compose v2
- Node.js 20+ and npm

## Quick Start

### Docker (full stack)

```bash
git clone https://github.com/Bbar0n234/learnflow-ai.git
cd learnflow-ai

# Set up environment
cp .env.example .env
# Edit .env — set API keys (OPENAI_API_KEY, etc.)

# Build and start
make docker-build && make docker-up

# App available at http://localhost:8000
```

### Local dev (DB in Docker, app locally)

```bash
# Install dependencies
uv sync
cd frontend && npm install && cd ..

# Set up environment
cp .env.local.example .env.local

# Start PostgreSQL
make docker-up-db

# Run backend and frontend dev servers (in separate terminals)
make dev      # backend at http://localhost:8000
make dev-fe   # frontend at http://localhost:5173
```

## Development

### Make Commands

| Command | Description |
|---------|-------------|
| `make docker-up` | Start full stack (app + db) |
| `make docker-up-db` | Start only PostgreSQL (for local dev) |
| `make docker-down` | Stop all containers |
| `make docker-build` | Build Docker images |
| `make docker-logs` | Show app container logs |
| `make lint` | Run ruff linter |
| `make format` | Format Python code |
| `make type-check` | Run mypy type checking |
| `make check` | Run all backend checks (lint + format-check + type-check) |
| `make lint-fe` | Run ESLint on frontend |
| `make format-fe` | Format frontend code with Prettier |
| `make test` | Run pytest |
| `make dev` | Run backend dev server |
| `make dev-fe` | Run frontend dev server |

### Environment Modes

- **Docker** (`.env`) — full stack in containers, app at `http://localhost:8000`
- **Local dev** (`.env.local`) — PostgreSQL in Docker, backend + frontend run locally

## Documentation

All project documentation is in the `doc/` directory:

- [idea.md](doc/idea.md) — What we're building and why
- [vision.md](doc/vision.md) — Technical vision and architecture
- [doc/product/](doc/product/) — Product documentation
- [doc/tech/](doc/tech/) — Technical documentation and ADRs
- [doc/tasks/](doc/tasks/) — Task lists and iterations

## License

MIT
