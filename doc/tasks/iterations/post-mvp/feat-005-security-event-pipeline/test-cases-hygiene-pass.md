# Test Cases — Codebase Hygiene Pass

Документ для агента-тестировщика, проверяющего **только** изменения hygiene pass (коммиты `27aa9a7`, `a4a96b4` и последующий env-cleanup). Полный регресс feat-005 уже выполнен и зафиксирован в основном `test-cases.md` — здесь не повторяем.

## Принцип отбора

Проверяем то, что мог сломать рефакторинг:

- структурный переезд `packages/siem-service` → `services/siem-service`,
- изменения раскладки модулей внутри `siem_service/`,
- удаление module-level singleton,
- удаление `bootstrap_admin`,
- унификацию env-файлов,
- ruff-конфиг и enforcement локальных импортов.

Бизнес-логика, корреляция, REST API, фронтенд — не трогалось, не ретестим.

## Контекст для тестировщика

| Что нужно | Где взять |
|-----------|-----------|
| Свежий клон/worktree на ветке `pmvp/feat-005-security-event-pipeline` | git |
| `.env`, `.env.local` поверх `.env.example`/`.env.local.example` | скопировать локально, заполнить секреты |
| Docker, docker compose, uv, GNU make | окружение проекта |

Перед началом — `git log --oneline -5`, должны быть видны коммиты hygiene pass.

---

## TC-1. Static checks

Проверяем, что стандартные quality gates зелёные после рефакторинга.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 1.1 | `make check` | exit 0. ruff check + ruff format check + mypy: «Success: no issues found in 145 source files» |
| 1.2 | `make lint` | exit 0. «All checks passed!» |
| 1.3 | `make type-check` | exit 0. mypy без ошибок по `backend/` и `services/siem-service/` |

## TC-2. Ruff enforces local-import rule

Проверяем, что `PLC0415` действительно ловит проблему — иначе конвенция декларативная, без enforcement.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 2.1 | Открыть любой модуль в `backend/app/` (например, `app/main.py`), внутрь существующей функции добавить строку `import os`. Запустить `make lint` | exit ≠ 0. ruff пишет: `PLC0415 import-outside-toplevel` с указанием файла и строки. Откатить добавленную строку |
| 2.2 | В тот же файл вместо «голого» добавить `import os  # lazy: testing` | Откатить вставку. (Само правило `PLC0415` без `# noqa: PLC0415` всё равно сработает — комментарий `# lazy:` это ритуал для ревью, не подавление; для подавления используется `# noqa: PLC0415`) |

## TC-3. Workspace structure

Проверяем переезд директории и согласованность ссылок.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 3.1 | `ls services/siem-service/siem_service/` | Видны `domain/`, `infra/`, `pipeline/`, `correlation/`, `api/`, плюс `main.py`, `config.py`, `repositories.py`, `services.py`, `__init__.py`. Файлов `models.py`, `schemas.py`, `db.py`, `auth.py`, `subscriber.py`, `event_writer.py`, `meta_emitter.py`, `supervisor.py` в корне **нет** |
| 3.2 | `ls packages/siem-service` | Директория не существует — `No such file or directory` |
| 3.3 | `ls backend/Dockerfile` и `ls Dockerfile` | первый существует, второй — нет |
| 3.4 | `grep -rn "packages/siem-service" --include="*.py" --include="*.yml" --include="*.toml" --include="Makefile" --include="Dockerfile"` | Только исторические упоминания в `doc/tasks/iterations/.../plan.md` (план до реализации). Никаких ссылок в `Makefile`, `docker-compose.yml`, `pyproject.toml`, исходниках |
| 3.5 | `grep -rn "from siem_service\.\(models\|schemas\|db\|auth\|subscriber\|event_writer\|meta_emitter\|supervisor\)\b" services/siem-service` | Пусто. Все импорты идут через подпакеты |

## TC-4. Container build & startup

Проверяем, что Dockerfile-ы собираются с новых путей и стек поднимается.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 4.1 | `docker compose build app` | Сборка успешна. Stage 1 (frontend) и stage 2 (backend) проходят. uv ставит зависимости через `uv sync --locked --all-packages` |
| 4.2 | `docker compose build siem-service` | Сборка успешна. Используется `services/siem-service/Dockerfile` с pin-версией uv `0.10.2`. Cache mount `--mount=type=cache,target=/root/.cache/uv` отрабатывает |
| 4.3 | `docker compose up -d` | Все 4 сервиса (`db`, `redis`, `siem-db`, `app`, `siem-service`) поднимаются и переходят в `healthy` (через `docker compose ps`) |
| 4.4 | `docker compose logs app` (последние 200 строк) | Нет `ImportError`, `AttributeError`, `ModuleNotFoundError`. Видна строка `app started`. Если Redis доступен — `security event publisher started` |
| 4.5 | `docker compose logs siem-service` (последние 200 строк) | Нет `ImportError`. Subscriber и correlation engine стартуют (видно по `"subscriber started"` или аналогичному `info` событию) |

## TC-5. Singleton removal — runtime behavior

Проверяем, что транспорт security-событий работает после удаления module-level singleton.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 5.1 | На поднятом стеке: попытка логина с заведомо неверным паролем через `POST /api/auth/login` (любой существующий или несуществующий user) | Ответ 401. В логах `app` — `auth.login.failed` или похожее security-событие |
| 5.2 | `docker compose exec redis redis-cli XLEN security.events` | Длина потока > 0 (значение увеличилось после действия 5.1). Подтверждает: producer (login route) → structlog processor → holder → RedisEventTransport → Redis работает end-to-end через closure |
| 5.3 | `docker compose exec siem-db psql -U siem -d siem -c "SELECT count(*) FROM siem_events WHERE event_type LIKE 'auth.login.%';"` | Значение увеличилось после действия 5.1 (с учётом небольшой задержки на subscriber tick). Подтверждает: consumer (siem-service) работает, схема и пути не сломались |
| 5.4 | `docker compose exec app python -c "from app.security_pipeline.transport import EventTransportHolder, RedisEventTransport; print('ok')"` | Печатает `ok`, без `ImportError`. Импорт удалённых имён `get_transport`, `set_transport`, `_transport` упасть не должен — но и не должен существовать: `python -c "from app.security_pipeline.transport import get_transport"` — `ImportError` |

## TC-6. Bootstrap admin removal

Проверяем, что автоматический промоут убран и работает только CLI.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 6.1 | `grep -rn "INITIAL_ADMIN\|bootstrap_admin" backend/ .env.example .env.local.example docker-compose.yml` | Пусто (исключая исторические упоминания в `doc/tasks/iterations/.../`) |
| 6.2 | `ls backend/app/bootstrap.py` | Файл не существует |
| 6.3 | На свежей БД (`docker compose down -v && docker compose up -d`): дождаться `app` healthy, посмотреть логи | В логах **нет** `initial_admin_user_not_found`, `admin_bootstrapped`, `no initial admin username configured`. Старт чистый |
| 6.4 | `make grant-admin` без аргументов | exit 1, сообщение `Usage: make grant-admin USER=<username>` |
| 6.5 | `make grant-admin USER=nobody-such-user` | exit 1, сообщение `User 'nobody-such-user' not found. Register first, then grant admin.` Пользователь не создаётся, БД не меняется |
| 6.6 | Зарегистрировать пользователя через `POST /api/auth/register` (например, username `tester`). Затем `make grant-admin USER=tester` | exit 0, сообщение `User 'tester' granted admin privileges.`. В БД: `SELECT is_admin FROM users WHERE name='tester';` → `t` |
| 6.7 | Повторно `make grant-admin USER=tester` | exit 0, сообщение `User 'tester' is already an admin.` Идемпотентно |

## TC-7. Env vars — single source of truth

Проверяем унификацию env-файлов.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 7.1 | `ls services/siem-service/.env.example` | Файл не существует |
| 7.2 | `cat .env.example` | Содержит секцию `# ───────── SIEM service ─────────` со всеми SIEM-переменными: `SIEM_POSTGRES_USER`, `SIEM_POSTGRES_PASSWORD`, `SIEM_POSTGRES_DB`, `SIEM_FRONTEND_ORIGIN`, `SIEM_XREAD_BATCH_SIZE`, `SIEM_XREAD_BLOCK_MS`, `SIEM_POLL_INTERVAL_SECONDS`, `SIEM_DELETE_AFTER_DAYS`, `SIEM_ALERT_OPEN_WINDOW_SECONDS` |
| 7.3 | `grep -E "SIEM_" docker-compose.yml` (секция `siem-service.environment`) | Все SIEM-параметры используют форму `${VAR:-default}` substitution. Хардкодов значений нет |
| 7.4 | В `.env` локально выставить `SIEM_ALERT_OPEN_WINDOW_SECONDS=300`, `docker compose up -d siem-service`. `docker compose exec siem-service env \| grep SIEM_ALERT_OPEN_WINDOW_SECONDS` | `SIEM_ALERT_OPEN_WINDOW_SECONDS=300`. Значение из `.env` дошло до контейнера, override без правки compose работает |
| 7.5 | После 7.4: спровоцировать создание alert (например, через >5 неудачных логинов с одного IP, см. baseline rules). Затем сразу же ещё один — должен попасть в **тот же** alert (open window 300s ≫ время теста). Подождать > 5 мин и спровоцировать ещё одно событие | До истечения 300s — события агрегируются в существующий alert (`matched_events_count++`). После 300s — создаётся новый alert. Подтверждает: `Settings.alert_open_window_seconds` действительно прокинут в `deduper.py`, не висит как заглушка |

## TC-8. Migrations & schema

Проверяем, что миграции применяются на новых путях.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 8.1 | На поднятой `db`: `make migrate` | exit 0. Все миграции main app проходят, включая `add_is_admin_to_users` |
| 8.2 | На поднятой `siem-db`: `make migrate-siem` | exit 0. Все 4 миграции siem-service проходят. (Путь `cd services/siem-service` в Makefile теперь актуальный) |
| 8.3 | `cat backend/alembic/versions/add_is_admin_to_users.py \| head -10` | Шапка содержит `# Manual migration: ... scheduled for regeneration`. Это маркер для будущего follow-up, не функциональный блокер |

## TC-9. Conventions documentation reachability

Sanity-check: правила, которые должны видеть и архитектор, и агент.

| ID | Действие | Ожидаемое |
|----|----------|-----------|
| 9.1 | `grep -n "Hard Rules" CLAUDE.md` | Секция найдена. Содержит one-liner'ы по: DB migrations, Imports, Interfaces, Module-level state, Env vs constants, Workspace layout |
| 9.2 | `grep -n "Before editing code" CLAUDE.md` | Императив `Before editing code on a non-trivial task, open doc/tech/conventions.md` присутствует |
| 9.3 | `grep -nE "^## (Структура проекта\|Database migrations\|Module-level state)" doc/tech/conventions.md` и `grep -nE "^### (Импорты\|Интерфейсы\|Что попадает в env)" doc/tech/conventions.md` | Все секции присутствуют. Читаемы |

---

## Out of scope

Эти кейсы **не нужно** выполнять — они не относятся к hygiene pass:

- Сценарии prompt-injection защиты (Sec 1.0/2.0).
- REST API contract тесты (events/alerts/rules) — поведение не менялось.
- Frontend Security page — не трогалась.
- End-to-end сценарии генерации alerts по полному набору baseline rules.
- Корреляция rule types `threshold`/`sequence`/`aggregate` — реализация без изменений (сменилось только базовое объявление с `ABC` на `Protocol`).
- Rate limiting и token replay-detection.

## Формат отчёта

Для каждого TC: `PASS` / `FAIL` / `SKIP`. Для `FAIL` — фактический вывод (последние 30 строк log/console), отличие от ожидаемого, гипотеза причины. Для `SKIP` — почему (например, не удалось поднять Docker).

Если TC-5.4 показывает `ImportError` — это **критическая регрессия**, останавливаем тестирование, эскалируем архитектору.

Если TC-7.4 не передаёт значение в контейнер — проблема substitution в compose, фикс перед merge.

Остальные FAIL — приоритет по уровню воздействия (build → runtime → конвенции).
