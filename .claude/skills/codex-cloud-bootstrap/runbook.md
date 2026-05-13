# Codex Cloud setup runbook

Готовые блоки для копи-паста в Codex Environment UI (`chatgpt.com/codex/settings/environments`).

## Codex Environment UI: Setup script (one-time, cached ~12h)

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

## Environment variables

Указываются в Codex Environment UI → Environment variables.

**Обязательные:**

- `DATABASE_URL` = `postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow`
  Host = `localhost` (а не `db` как в локальном `.env`), потому что backend в Codex запускается процессом, не контейнером в docker-сети.
- `JWT_SECRET` — секрет подписи JWT, минимум 32 символа.

**Рекомендуемые** (без них backend стартует с warnings, часть фич disabled):

- `REDIS_URL` = `redis://localhost:6379/0`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`
- `CANARY_SECRET`, `MCP_ENCRYPTION_KEY`
- `FIRECRAWL_API_KEY`, `TAVILY_API_KEY`

Реальные dev-значения хранятся в локальной шпаргалке архитектора (`cloud-env-setup.md`, в `.gitignore`).

## Network policy

Agent phase: **Trusted** (полный интернет). Без этого `apt` / `uv` / `npm` не работают.

## Verification flow

```bash
make migrate
make check
make dev          # background или второе окно
curl http://127.0.0.1:8000/health   # ожидаем {"status":"ok"}
# kill make dev

make check-fe
make dev-fe       # background или второе окно
curl http://localhost:5173          # HTML ответ
# kill make dev-fe

make test         # в текущем Makefile exit 5 (no tests) трактуется как success
```

Все шаги должны быть зелёными.

## Known limitations

- **Docker / docker-compose недоступны** — sandbox `codex-universal` не содержит docker CLI. Все `make docker-*` таргеты неприменимы.
- **PR агент сам не мержит** в `develop` — merge выполняет архитектор локально (cloud merge-policy, `conventions.md` § Cloud sessions).
- **Имя ветки при push'е** — Codex обычно переименовывает feature-ветку в `codex/<name>`. Не блокер, учитывать при поиске на GitHub.

## Codex Cloud vs Claude Code on the web

| | Codex Cloud | Claude Code on the web |
|---|---|---|
| Docker | ❌ нет CLI | ✅ полноценно |
| Python в образе | 3.14 (нужен `uv python install 3.12`) | 3.12 (matches проект) |
| Корневой entry-file для агента | `AGENTS.md` (родной формат) | `CLAUDE.md` (родной формат) |
| Skills auto-discovery | `.agents/skills/` | `.claude/skills/` |
| Browser automation | ❌ (нет docker + строгий network) | ❌ (HTTP CONNECT не проходит, issue #11791) |

В этом репо `AGENTS.md` → symlink на `CLAUDE.md`, а `.agents/skills` → symlink на `.claude/skills`, поэтому source of truth для обоих стэков один.
