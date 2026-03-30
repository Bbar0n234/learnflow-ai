# chore-001: CI/CD + Deploy — Summary

## Что сделано

### CI workflow (`.github/workflows/ci.yml`)

Триггер: `pull_request` → develop, main. Один job `check`:
1. Setup uv (с кэшем) + Node 22 (с кэшем npm)
2. Install backend (`uv sync`) и frontend (`npm ci`) зависимостей
3. Restore mypy cache (`actions/cache`)
4. `make check` — ruff format --check, ruff check, mypy
5. `make check-fe` — tsc -b --noEmit, ESLint, Prettier --check
6. Frontend build (`npm run build`)
7. Docker build verification (`cp .env.example .env && docker compose build`)
8. `make test` (continue-on-error: true — placeholder до появления тестов)

### CD workflow (`.github/workflows/deploy.yml`)

Триггер: `push` → main. Concurrency guard (`cancel-in-progress: false`).
SSH Action (`appleboy/ssh-action@v1`) подключается к серверу и выполняет:
`git pull` → `docker compose build` → `docker compose up -d` → health check (poll `/health` каждые 2с, таймаут 60с).

### Makefile: `check-fe` target

Новый target — полный аналог backend `check` для frontend:
- `tsc -b --noEmit` — проверка типов через project references
- `eslint .` — линтинг
- `prettier --check .` — форматирование

### Инфраструктура

- Deploy SSH keypair (ED25519) на сервере, приватный ключ в GitHub Secret
- GitHub Secrets: `SSH_PRIVATE_KEY`, `SSH_HOST`, `SSH_USER`
- Branch protection ruleset для develop и main: restrict deletions, block force pushes
- Nginx: убрана basic auth (заменена JWT auth из feat-002), порт app привязан к 127.0.0.1

## Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `.github/workflows/ci.yml` | Создан |
| `.github/workflows/deploy.yml` | Создан |
| `Makefile` | Добавлен `check-fe` target |
| `CLAUDE.md` | Добавлен `check-fe` в таблицу команд |
| `docker-compose.yml` | Порт app: `8000:8000` → `127.0.0.1:8000:8000` |
| `frontend/src/shared/api/client.ts` | Фикс TypeScript ошибки в `ensureFreshToken` |
| `doc/tech/adr/ADR-012-ci-cd-deploy.md` | `lint-fe` → `check-fe` |
| `doc/tasks/iterations/production/chore-001-ci-cd/design-brief.md` | `lint-fe` → `check-fe` |
| `doc/tasks/tasklist-production.md` | Статус → Done, чеклист, артефакты |
| `doc/tasks/iterations/production/chore-001-ci-cd/plan.md` | Создан |
| `doc/tasks/iterations/production/chore-001-ci-cd/summary.md` | Создан |

## Найденные проблемы и решения

1. **`tsc --noEmit` не проверял файлы** — корневой `tsconfig.json` использует project references (`"files": []`). Заменён на `tsc -b --noEmit`.
2. **TypeScript strict error в `client.ts`** — `token.split(".")[1]` возвращает `string | undefined` при `noUncheckedIndexedAccess: true`. Добавлена валидация длины + non-null assertion.
3. **Незакоммиченные изменения на сервере** — `docker-compose.yml` правился вручную (порт 127.0.0.1). Закоммичено в репо.
4. **Nginx basic auth конфликтовал с JWT** — `Authorization` header перехватывался Nginx. Basic auth убран.
5. **Nginx sites-available vs sites-enabled рассинхрон** — `sites-enabled/learnflow` был обычным файлом, не симлинком. Обновлён вручную.

## Ручные шаги (выполнены)

- [x] SSH keypair сгенерирован на сервере, публичный ключ в `authorized_keys`
- [x] GitHub Secrets настроены
- [x] Branch protection ruleset создан
- [x] Nginx basic auth убран, конфиг обновлён
- [x] `.env` на сервере пересоздан с актуальными переменными (включая `JWT_SECRET`)
- [x] БД пересоздана (`docker compose down -v`)
