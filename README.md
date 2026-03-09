# LearnFlowAI

AI-powered tool for tech speakers and presenters to structure and prepare educational materials.

> **Status:** v2 in development (clean rewrite using AIDD methodology)

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker and Docker Compose v2
- Node.js 20+ and npm

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Bbar0n234/learnflow-ai.git
cd learnflow-ai

# Install Python dependencies
uv sync

# Set up environment
cp .env.local.example .env.local

# Start PostgreSQL
make docker-up

# Backend and frontend dev servers will be available in Phase D
```

## Development

### Make Commands

| Command | Description |
|---------|-------------|
| `make docker-up` | Start PostgreSQL |
| `make docker-down` | Stop all containers |
| `make docker-build` | Build Docker images |
| `make lint` | Run ruff linter |
| `make format` | Format Python code |
| `make type-check` | Run mypy type checking |
| `make check` | Run all backend checks (lint + format-check + type-check) |
| `make lint-fe` | Run ESLint on frontend |
| `make format-fe` | Format frontend code with Prettier |
| `make test` | Run pytest |
| `make dev` | Run backend dev server (Phase D) |
| `make dev-fe` | Run frontend dev server (Phase D) |

### Environment Modes

- **Docker** (`.env`) — full stack in containers
- **Local dev** (`.env.local`) — infrastructure (PostgreSQL) in containers, application runs locally

## Documentation

All project documentation is in the `doc/` directory:

- [idea.md](doc/idea.md) — What we're building and why
- [vision.md](doc/vision.md) — Technical vision and architecture
- [doc/product/](doc/product/) — Product documentation
- [doc/tech/](doc/tech/) — Technical documentation and ADRs
- [doc/tasks/](doc/tasks/) — Task lists and iterations

## License

MIT
