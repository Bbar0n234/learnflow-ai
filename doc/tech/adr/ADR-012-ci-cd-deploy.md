# ADR-012: CI/CD & Deploy Strategy

## Статус

Принято

## Контекст

Текущее состояние: качество кода обеспечивается только pre-commit hooks локально. Деплой ручной — SSH на VM, `git pull`, `docker compose build`, `docker compose up -d`. Нет автоматических проверок на PR, нет автоматического деплоя.

Проект: pet-project, один разработчик, одна VM с Nginx reverse proxy, single-container Docker-образ (frontend вбандлен в backend). Репозиторий на GitHub.

Нужно: автоматические проверки на PR (CI) + автоматический деплой при merge в main (CD).

## Решения

### CI/CD платформа: GitHub Actions

Репозиторий на GitHub — GitHub Actions нативно интегрирован, бесплатный tier покрывает потребности. Альтернативы не рассматривались.

### CI: проверки на pull request

Триггер: `on: pull_request` → develop и main. Запускает те же проверки, что pre-commit hooks, плюс build verification:
- `make check` (ruff format --check + ruff check + mypy)
- `make check-fe` (ESLint + Prettier)
- Frontend build (Vite)
- Docker build (проверка что образ собирается)
- `make test` (когда появятся тесты)

Кэширование зависимостей (uv, npm, mypy) — стандартная оптимизация, не архитектурное решение.

### Механизм деплоя: SSH Action

GitHub Actions runner подключается к серверу по SSH и выполняет команды: `git pull`, `docker compose build`, `docker compose up -d`, health check.

**Отклонено:**
- **Self-hosted runner** — нужно устанавливать и поддерживать runner-демон на сервере, дополнительная attack surface. Для одного проекта на одной VM — overkill без преимуществ.
- **Docker registry (GHCR)** — нужна авторизация registry на сервере, изменение docker-compose.yml (`build:` → `image:`). Преимущества (версионирование образов, разгрузка сервера при сборке) не оправданы при одной VM и одном образе.

### Сборка образа: на сервере

`git pull` + `docker compose build` непосредственно на сервере. Идентично тому, что делается при ручном деплое. Docker registry не используется.

### Политика деплоя: main = production

- `develop` — интеграционная ветка. CI-проверки на PR. Merge в develop не триггерит деплой.
- `main` — зеркало production. Merge в main триггерит CD (auto-deploy на сервер).

Отдельного dev-стенда нет, один сервер = production. Деплой на merge в develop отклонён — каждый merge фичи сразу в прод слишком рискован без буфера.

### Downtime: простой restart

`docker compose up -d` останавливает старый контейнер и запускает новый. Даунтайм 5-15 секунд. Для pet-проекта с одним пользователем — приемлемо.

Blue-green/rolling deployment не рассматривался — несоразмерная сложность для текущего масштаба.

## Следствия

- 3 секрета в GitHub Settings: `SSH_PRIVATE_KEY`, `SSH_HOST`, `SSH_USER`
- Deploy SSH-ключ на сервере (отдельная keypair для CI/CD)
- CI блокирует merge при провале проверок (branch protection)
- Деплой-скрипт не зависит от feat-002 (auth) — после реализации аутентификации Nginx basic auth убирается отдельно, pipeline не меняется
