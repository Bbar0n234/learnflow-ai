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
```

Setup script выполняет тяжёлую подготовку: системные пакеты, Python 3.12 и зависимости uv workspace.

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
```

Maintenance script выполняет лёгкую runtime-подготовку при resume cached container: стартует Postgres/Redis и гарантирует наличие role/database.

## Environment variables

Указываются в Codex Environment UI -> Environment variables.

Минимально:

```text
DATABASE_URL=postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<dev-secret-at-least-32-characters>
```

Опционально для полной проверки agent/observability/web-фич:

```text
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=...
CANARY_SECRET=...
MCP_ENCRYPTION_KEY=...
FIRECRAWL_API_KEY=...
TAVILY_API_KEY=...
```

`DATABASE_URL` и `REDIS_URL` используют `localhost`, а не `db` / `redis`: backend в Codex Cloud запускается процессом, не контейнером внутри docker-сети.

Codex Cloud **Secrets** доступны только setup phase и удаляются до agent phase. Значения, которые нужны backend/agent во время работы, должны быть Environment variables. Используй только dev-ключи с ограниченными правами.

## Verification

После сохранения environment запусти новую Codex task на нужной ветке и попроси агента выполнить проверку без изменений в коде:

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
8. запусти make dev, проверь /health, останови сервер
9. запусти make dev-fe, проверь что localhost:5173 отдаёт HTML, останови сервер
Верни краткий отчёт: что прошло, что упало, какие env vars видны без печати секретов.
```

Ожидаемый результат:

```text
Python 3.12 используется в uv environment
pg_isready OK
redis-cli ping -> PONG
make migrate OK
make check OK
make check-fe OK
make dev поднимает backend
GET /health -> {"status":"ok"}
make dev-fe поднимает frontend
curl localhost:5173 возвращает HTML
```

## Known limitations

- Docker / docker-compose в Codex Cloud недоступны. Не используй `make docker-*` в cloud-сессиях.
- Postgres и Redis запускаются локальными процессами внутри Codex container.
- Агент не мержит PR в `develop`: cloud merge-policy описана в [conventions.md](../conventions.md#cloud-sessions-async-workflow).
- UI/integration validation остаётся за архитектором локально после pull feature-ветки.

## Related docs

- [doc/tech/conventions.md](../conventions.md) — cloud merge-policy и общие правила проекта.
- [AGENTS.md](../../../AGENTS.md) — agent-facing инструкции проекта.
- `.claude/skills/codex-cloud-bootstrap/SKILL.md` — runtime policy для агента внутри Codex Cloud.
