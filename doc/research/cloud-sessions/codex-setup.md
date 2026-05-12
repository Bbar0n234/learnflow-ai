# Codex Cloud setup (docker-less)

## Scope
Runbook для OpenAI Codex Cloud (`codex-universal`) без Docker: process-based PostgreSQL + Redis + FastAPI + Vite.

## Codex Environment UI: Setup script (one-time, cached)
```bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y postgresql-16 redis-server

uv python install 3.12
uv sync --all-packages --python 3.12
```

## Codex Environment UI: Maintenance script (each resume)
```bash
set -euo pipefail

sudo pg_ctlcluster 16 main start || true
redis-server --daemonize yes || true

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE learnflow LOGIN PASSWORD 'learnflow';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE learnflow OWNER learnflow;"
```

## Required env vars
Указывать в Codex Environment Variables (значения хранятся вне репозитория):

- `DATABASE_URL` — SQLAlchemy URL backend БД (для cloud-процесса обычно `postgresql+psycopg://learnflow:<password>@localhost:5432/learnflow`).
- `JWT_SECRET` — обязательный секрет подписи JWT (минимум 32 символа).

Recommended для полного dev-поведения:
- `REDIS_URL` — URL Redis (`redis://localhost:6379/0` для локального cloud runtime).
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` — observability/instrumentation.
- `CANARY_SECRET` — canary protection в security guard.
- `MCP_ENCRYPTION_KEY` — шифрование user MCP API keys.
- `FIRECRAWL_API_KEY`, `TAVILY_API_KEY` — внешние MCP/tool integrations.

## Verification flow
```bash
make migrate
make check
make dev
# second terminal
curl http://127.0.0.1:8000/health

make check-fe
make dev-fe
# second terminal
curl http://localhost:5173

make test
```

## Known limitations
- Docker / docker-compose недоступны архитектурно в `codex-universal`.
- `make test` сейчас может завершаться с `exit code 5` при `no tests collected`; это текущее поведение Makefile и требует отдельного решения в репозитории.
- При пустых optional secrets backend стартует, но пишет предупреждения (Langfuse/MCP/Canary disabled).
- Встроенные remote MCP endpoints могут отвечать 5xx и отключаться на startup guard-проверке; это внешний фактор, не блокирующий `/health`.

## Codex Cloud vs Claude Code on the web (кратко)
- Codex Cloud: нет Docker, требуется явный process-based bootstrap в Environment scripts.
- Claude Code web: чаще используется через существующие проектные инструкции в `CLAUDE.md`; bootstrap-подход может отличаться в зависимости от sandbox-конфига.
- Для обоих режимов source-of-truth по архитектуре и правилам одинаковый: `doc/` + `doc/tech/conventions.md`.
