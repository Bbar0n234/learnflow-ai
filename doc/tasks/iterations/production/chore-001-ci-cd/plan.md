# Implementation Plan: chore-001 — CI/CD + Deploy

## Context

Проект не имеет CI/CD. Качество кода обеспечивается только локальными pre-commit hooks. Деплой ручной: SSH на VM, `git pull`, `docker compose build`, `docker compose up -d`. Цель итерации — автоматические проверки на PR (CI) + автоматический деплой при merge в main (CD).

## Референсы

| Документ | Путь |
|----------|------|
| ADR-012: CI/CD & Deploy | `doc/tech/adr/ADR-012-ci-cd-deploy.md` |
| Design Brief | `doc/tasks/iterations/production/chore-001-ci-cd/design-brief.md` |
| Tasklist | `doc/tasks/tasklist-production.md` |
| Conventions | `doc/tech/conventions.md` |
| Workflow | `doc/workflow.md` |

## Согласованные решения

1. **Frontend CI gate** — новый target `check-fe` (ESLint + Prettier --check), по аналогии с backend `check`. Существующий `lint-fe` без изменений. Документация (таск-лист, ADR-012, design brief) обновляется: `make lint-fe` → `make check-fe` как CI gate. *(Согласовано с архитектором)*

2. **`make test`** — включаем шаг с `continue-on-error: true`, placeholder до появления тестов. *(Согласовано с архитектором)*

3. **Concurrency guard на CD** — `concurrency: { group: deploy, cancel-in-progress: false }` предотвращает параллельные деплои при быстрых последовательных merge в main.

3. **`.env` для docker build в CI** — `cp .env.example .env` перед `docker compose build`. Переменные в `docker-compose.yml` имеют defaults (`${VAR:-default}`), но `env_file: - .env` на app-сервисе может валидироваться.

4. **npm cache path** — `package-lock.json` в `frontend/`, не в корне. `actions/setup-node` требует явного `cache-dependency-path: frontend/package-lock.json`.

## Шаги реализации

### Шаг 1: Makefile — добавить `check-fe` target

**Файл:** `Makefile`

```makefile
check-fe:  ## Run all frontend checks (CI gate)
	cd frontend && npx eslint .
	cd frontend && npx prettier --check .
```

Добавить в `.PHONY` строку.

### Шаг 2: CI workflow

**Файл:** `.github/workflows/ci.yml` (создать)

```yaml
name: CI

on:
  pull_request:
    branches: [develop, main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Setup uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json

      - name: Install backend dependencies
        run: uv sync

      - name: Install frontend dependencies
        run: cd frontend && npm ci

      - name: Restore mypy cache
        uses: actions/cache@v4
        with:
          path: .mypy_cache
          key: mypy-${{ hashFiles('**/*.py') }}
          restore-keys: mypy-

      - name: Backend checks
        run: make check

      - name: Frontend checks
        run: make check-fe

      - name: Frontend build
        run: cd frontend && npm run build

      - name: Docker build verification
        run: |
          cp .env.example .env
          docker compose build

      - name: Tests
        run: make test
        continue-on-error: true
```

### Шаг 3: CD workflow

**Файл:** `.github/workflows/deploy.yml` (создать)

```yaml
name: Deploy

on:
  push:
    branches: [main]

concurrency:
  group: deploy
  cancel-in-progress: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ${{ secrets.SSH_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            set -e
            cd ~/learnflow-ai
            git pull origin main
            docker compose build
            docker compose up -d
            echo "Waiting for health check..."
            for i in $(seq 1 30); do
              if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
                echo "Health check passed"
                exit 0
              fi
              sleep 2
            done
            echo "Health check failed after 60s"
            exit 1
```

### Шаг 4: Ручные шаги

**Deploy keypair:**
1. Сгенерировать ED25519 keypair: `ssh-keygen -t ed25519 -C "github-actions-deploy"`
2. Публичный ключ → `~/.ssh/authorized_keys` на сервере
3. Приватный ключ → GitHub Secret `SSH_PRIVATE_KEY`

**GitHub Secrets** (Settings → Secrets and variables → Actions):
- `SSH_PRIVATE_KEY` — приватный ключ
- `SSH_HOST` — IP/домен сервера
- `SSH_USER` — пользователь на сервере

**Branch protection rules** (Settings → Branches → Add rule):
- Для `develop` и `main`:
  - Require status checks to pass: `check`
  - Require branches to be up to date before merging

### Шаг 5: Синхронизация документации (`lint-fe` → `check-fe`)

- **`doc/tasks/tasklist-production.md`** — состав работ и критерии приёмки: `make lint-fe` → `make check-fe`
- **`doc/tech/adr/ADR-012-ci-cd-deploy.md`** — секция CI: `make lint-fe` → `make check-fe`
- **`doc/tasks/iterations/production/chore-001-ci-cd/design-brief.md`** — step 7: `make lint-fe` → `make check-fe`

### Шаг 6: Документация итерации

- `doc/tasks/iterations/production/chore-001-ci-cd/plan.md` — сохранить этот план
- `doc/tasks/tasklist-production.md` — обновить статус chore-001 → 🚧 In Progress
- После реализации: `summary.md`, обновить статус → ✅ Done
