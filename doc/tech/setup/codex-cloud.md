# Codex Cloud setup

Инструкция для настройки ChatGPT Codex Environment под `learnflow-ai`.

Этот документ предназначен для человека, который впервые подключает репозиторий к Codex Cloud. Agent-facing runtime rules живут отдельно в skill `codex-cloud-bootstrap`: агент должен знать, как работать в уже подготовленном окружении, но не должен держать setup runbook в регулярном контексте.

## Runtime model

Codex Cloud запускает задачу в две фазы:

1. Платформа создаёт container, checkout'ит репозиторий и выполняет **Setup script**.
2. После этого стартует agent phase: агент читает `AGENTS.md`, запускает команды, меняет код и валидирует результат.

Container state кешируется примерно на 12 часов. При resume cached container Codex выполняет optional **Maintenance script**. Cache инвалидируется при изменении setup script, maintenance script, environment variables или secrets.

Источник деталей: [Codex Cloud Environments](https://developers.openai.com/codex/cloud/environments).

## Environment settings

Открой `ChatGPT -> Codex -> Settings -> Environments` и создай environment для `learnflow-ai`.

Рекомендуемый shape:

| Setting | Value |
|---------|-------|
| Base image | `universal` / `codex-universal` |
| Agent internet access | Trusted / full internet для dev environment без production secrets |
| Setup script | блок из секции ниже |
| Maintenance script | блок из секции ниже |
| Environment variables | значения из секции ниже |

Setup script запускается с internet access. Agent phase по умолчанию без internet access, но для этого проекта cloud-agent обычно должен иметь доступ к package registries, GitHub/docs и web tooling, поэтому dev environment настраивается как trusted. Не добавляй production secrets в такой environment.

## Setup script

Вставить в Codex Environment UI -> Setup script.

```bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y postgresql-16 redis-server

uv python install 3.12
uv sync --all-packages --python 3.12

cd frontend
npm ci
cd ..

sudo pg_ctlcluster 16 main start || true
redis-server --daemonize yes || true

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE learnflow LOGIN PASSWORD 'learnflow';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE learnflow OWNER learnflow;"

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='siem'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE siem LOGIN PASSWORD 'siem';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='siem'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE siem OWNER siem;"
```

Setup script выполняет initial bootstrap: системные пакеты, Python 3.12, Python/frontend зависимости и создание локальных PostgreSQL databases. Блок запуска Postgres/Redis и создания role/database намеренно дублируется в Maintenance script: setup нужен для fresh container, maintenance — для resume cached container.

Не задавай runtime env через `export` внутри setup script: setup script запускается в отдельной Bash-сессии, поэтому такие значения не переходят в agent phase. Runtime env задаётся через Environment variables в UI.

## Maintenance script

Вставить в Codex Environment UI -> Maintenance script.

```bash
set -euo pipefail

sudo pg_ctlcluster 16 main start || true
redis-server --daemonize yes || true

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE learnflow LOGIN PASSWORD 'learnflow';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='learnflow'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE learnflow OWNER learnflow;"

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='siem'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE ROLE siem LOGIN PASSWORD 'siem';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='siem'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE siem OWNER siem;"
```

Maintenance script выполняет лёгкую runtime-подготовку при resume cached container: стартует Postgres/Redis и гарантирует наличие role/database для main backend и SIEM service.

## Environment variables

Указываются в Codex Environment UI -> Environment variables.

Минимально:

```text
POSTGRES_USER=learnflow
POSTGRES_PASSWORD=learnflow
POSTGRES_DB=learnflow
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow
REDIS_URL=redis://localhost:6379/0
REDIS_PORT=6379
JWT_SECRET=<dev-secret-at-least-32-characters>
```

Для SIEM service:

```text
SIEM_POSTGRES_USER=siem
SIEM_POSTGRES_PASSWORD=siem
SIEM_POSTGRES_DB=siem
SIEM_POSTGRES_PORT=5432
SIEM_DATABASE_URL=postgresql+asyncpg://siem:siem@localhost:5432/siem
SIEM_REDIS_URL=redis://localhost:6379/0
SIEM_JWT_SECRET=<same-as-JWT_SECRET>
SIEM_FRONTEND_ORIGIN=http://localhost:8000,http://localhost:5173
SIEM_XREAD_BATCH_SIZE=100
SIEM_XREAD_BLOCK_MS=1000
SIEM_POLL_INTERVAL_SECONDS=10
SIEM_DELETE_AFTER_DAYS=90
SIEM_ALERT_OPEN_WINDOW_SECONDS=86400
```

Для полной проверки agent/observability/web-фич:

```text
LLM_API_KEY=...
LLM_BASE_URL=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=...
LANGFUSE_TRACING_ENVIRONMENT=development
LANGFUSE_RELEASE=...
LANGFUSE_PROMPT_LABEL=latest
LANGFUSE_PROMPT_CACHE_TTL=300
CANARY_SECRET=...
MCP_ENCRYPTION_KEY=...
FIRECRAWL_API_KEY=...
TAVILY_API_KEY=...
```

`DATABASE_URL`, `SIEM_DATABASE_URL`, `REDIS_URL` и `SIEM_REDIS_URL` используют `localhost`, а не `db` / `redis` / `siem-db`: сервисы в Codex Cloud запускаются процессами, не контейнерами внутри docker-сети.

Codex Cloud **Secrets** доступны только setup phase и удаляются до agent phase. Значения, которые нужны backend/agent во время работы, должны быть Environment variables. Используй только dev-ключи с ограниченными правами.

## Verification

После сохранения environment запусти новую Codex task на нужной ветке и попроси агента выполнить проверку без изменений в коде.

Baseline checks:

```text
Проверь Codex Cloud environment для learnflow-ai. Ничего не меняй в коде.
Выполни:
1. python --version
2. uv run python --version
3. pg_isready
4. redis-cli ping
5. make migrate
6. make check
7. make check-fe
Верни краткий отчёт: что прошло, что упало, какие env vars видны без печати секретов.
```

Ожидаемый baseline результат:

```text
Python 3.12 используется в uv environment
pg_isready OK
redis-cli ping -> PONG
make migrate OK
make check OK
make check-fe OK
```

### HTTP smoke в Codex Cloud

Codex Cloud может проверять backend/frontend через localhost, но dev-server и HTTP probe должны выполняться внутри одной shell invocation. Ненадёжный паттерн:

```text
command 1: make dev
command 2: curl http://127.0.0.1:8000/health
```

В такой схеме процесс может продолжать жить, но socket не будет виден следующей command invocation из-за sandbox/network isolation. Failed cross-invocation `curl` не доказывает, что backend или frontend сломан.

Надёжный паттерн: launch + poll + teardown в одной shell-команде.

Backend HTTP smoke:

```bash
set -euo pipefail

make dev >/tmp/learnflow-backend.log 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health; then
    echo "backend-health-ok"
    exit 0
  fi
  sleep 1
done

echo "backend-health-failed"
tail -120 /tmp/learnflow-backend.log
exit 1
```

Frontend HTTP smoke:

```bash
set -euo pipefail

make dev-fe >/tmp/learnflow-frontend.log 2>&1 &
pid=$!
cleanup() { kill "$pid" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:5173/ >/tmp/learnflow-frontend.html; then
    echo "frontend-html-ok"
    head -20 /tmp/learnflow-frontend.html
    exit 0
  fi
  sleep 1
done

echo "frontend-html-failed"
tail -120 /tmp/learnflow-frontend.log
exit 1
```

Backend route checks без TCP можно делать in-process через FastAPI app и `httpx.ASGITransport` / `TestClient`. Это устойчивый fallback, когда HTTP listener не является предметом проверки.

## Known limitations

- Docker / docker-compose в Codex Cloud недоступны. Не используй `make docker-*` в cloud-сессиях.
- Postgres и Redis запускаются локальными процессами внутри Codex container.
- Long-running dev-server между отдельными command invocations ненадёжен для localhost HTTP checks. Используй launch + poll + teardown в одной shell invocation.
- Агент не мержит PR в `develop`: cloud merge-policy описана в [conventions.md](../conventions.md#cloud-sessions-async-workflow).
- UI/integration validation остаётся за архитектором локально после pull feature-ветки.

## Related docs

- [doc/tech/conventions.md](../conventions.md) — cloud merge-policy и общие правила проекта.
- [AGENTS.md](../../../AGENTS.md) — agent-facing инструкции проекта.
- `.claude/skills/codex-cloud-bootstrap/SKILL.md` — runtime policy для агента внутри Codex Cloud.
