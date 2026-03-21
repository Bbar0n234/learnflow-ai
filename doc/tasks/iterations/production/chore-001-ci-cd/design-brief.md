# chore-001: CI/CD + Deploy — Design Brief

Контекст реализации для implementation plan. Архитектурные решения: [ADR-012](../../../tech/adr/ADR-012-ci-cd-deploy.md).

## CI (ci.yml)

### Триггер

```yaml
on:
  pull_request:
    branches: [develop, main]
```

Runner: `ubuntu-latest`.

### Steps

1. Checkout (`actions/checkout`)
2. Setup Python 3.12 + uv (`astral-sh/setup-uv` с кэшем)
3. Setup Node 22 (`actions/setup-node` с кэшем npm)
4. Install backend deps (`uv sync`)
5. Install frontend deps (`cd frontend && npm ci`)
6. Backend checks (`make check` — ruff format --check, ruff check, mypy)
7. Frontend checks (`make lint-fe` — ESLint, Prettier)
8. Frontend build (`cd frontend && npm run build`)
9. Docker build verification (`docker compose build`)
10. Tests (`make test` — пока пустые, но step готов)

### Кэширование

| Что | Action / механизм | Ключ кэша |
|-----|-------------------|-----------|
| Python-пакеты | `astral-sh/setup-uv` встроенный кэш | хэш `uv.lock` |
| npm-пакеты | `actions/setup-node` с `cache: npm` | хэш `package-lock.json` |
| mypy | `actions/cache` для `.mypy_cache` | хэш `*.py` файлов |

### Branch protection

В GitHub Settings → Branches → Branch protection rules для `develop` и `main`:
- Require status checks to pass before merging
- Require branches to be up to date before merging

## CD (deploy.yml)

### Триггер

```yaml
on:
  push:
    branches: [main]
```

### Deploy sequence

SSH на сервер (`appleboy/ssh-action`), выполняет:

1. `cd ~/learnflow-ai`
2. `git pull origin main`
3. `docker compose build`
4. `docker compose up -d`
5. Health check — дождаться что приложение отвечает

### Health check

После `docker compose up -d` — проверить что контейнер `app` прошёл healthcheck (уже настроен в docker-compose.yml: `curl -f http://localhost:8000/health`). Варианты:
- `docker compose ps` — статус `healthy`
- Прямой `curl` к localhost:8000/health

При провале — workflow завершается с ошибкой, видно в GitHub Actions UI.

## Secrets

Настраиваются в GitHub → Settings → Secrets and variables → Actions:

| Secret | Значение |
|--------|----------|
| `SSH_PRIVATE_KEY` | Приватный ключ deploy keypair |
| `SSH_HOST` | IP-адрес или домен сервера |
| `SSH_USER` | Пользователь на сервере |

Подготовка на сервере: создать SSH keypair для деплоя, добавить публичный ключ в `~/.ssh/authorized_keys` пользователя деплоя.

## Scope boundaries (не chore-001)

- Уведомления о деплое (Telegram, Slack)
- Автоматический rollback
- Docker registry (GHCR)
- Staging environment
- Integration tests с внешними API (ANTHROPIC_API_KEY)
- Zero-downtime deployment
