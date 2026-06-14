# Summary: feat-004 — Backend / FastAPI Slice + SIEM Hygiene

Slice-аудит backend-инфраструктуры обоих сервисов (main app + siem-service) против skill `fastapi` + закрытие точечных техдолгов из бэклога. Ветка `cm/feat-004-fastapi`, PR #67 в `develop`. Develop с влитыми feat-002/feat-003 слит в ветку и конфликты разрешены (см. § Слияние).

## Что сделано

### Точечные техдолги из тасклиста

- **SIEM `MetaEmitter` singleton устранён.** Git-археология подтвердила: синглтон не был осознанным решением (родился как «Singleton factory» в T3, post-review fix лишь залатал sync/async Redis, hygiene pass устранил соседний `_transport`, а этот отложил). Теперь: создание в lifespan → `app.state.meta_emitter` → `MetaEmitterDep`; зависимость `get_redis_from_request` из routes исчезла за ненадобностью.
- **Дубль `SecurityEvent`/`SecurityIdentifiers` удалён** — emitter собирает контрактный `siem_contracts.SecurityEvent` (UUID `event_id`, `EventType` Literal, типизированная severity); все пять `siem.*` meta-типов уже были в vocabulary.
- **`CORS_ORIGINS` — CSV вместо JSON.** То же для `SIEM_FRONTEND_ORIGIN`. Детали развилки — § Решения, п.2.
- **SIEM follow-ups:** UP042 → `StrEnum` (аудит показал: все строковые пути идут через явный `.value`, опасение из TODO не подтвердилось); uv pin 0.10.2 → 0.11.21 в обоих Dockerfile. Отклонено архитектором — line-length 88→100 и пересоздание hand-written миграций (§ Решения, п.4–5).

### Findings аудита по skill (закрыты)

- **Module-level state:** `rate_limiter` (main app) → lifespan/`app.state`; SIEM `infra/db.py` глобали → фабрики + session-dependency из `app.state`; `CorrelationEngine` фабрика-синглтон (с ловушкой «poll_interval только при первом вызове») → конструирование в lifespan с инъекцией session_factory; глобальные task-переменные SIEM `main.py` → локальные переменные lifespan; SIEM перешёл на `create_app()`-фабрику зеркально main app.
- **`Settings()` на каждый запрос** (горячий путь `get_current_user`, auth-роуты, feedback) → один экземпляр в lifespan, `SettingsDep`; siem `@lru_cache get_settings` удалён (validator JWT — в `app.state.jwt_validator`).
- **Блокирующий код в async:** argon2 hash/verify (`AuthService`) → `anyio.to_thread.run_sync` (подтверждено стендом: серия логинов не блокирует `/health`); sync `httpx.delete` в feedback → `httpx.AsyncClient`; `langfuse.flush()` → to_thread; pdfkit в artifacts → to_thread (конвергентно с feat-002).
- **Annotated-стиль:** хвосты в main app (artifacts, chats, Cookie в auth) + полный перевод SIEM `routes.py` (новый `siem_service/api/deps.py`: `SessionDep`/`AdminPayload`/`MetaEmitterDep`); правило `B008` включено в ruff (ignore снят), ковёр `# noqa: B008` удалён.
- **Мелочи:** SIEM `config.py` → `SettingsConfigDict` (v2-стиль); `jwt_secret` обязателен (§ Решения, п.6); `SIEM_FRONTEND_ORIGIN` переехал из `os.environ` в `Settings`; дубль health `/api/security/health` удалён; мёртвый `env_file_encoding` в main `Settings` удалён; `class Config` → `ConfigDict` в `siem_contracts.events` (deprecation, всплыл в тестах); затенение `fastapi.status` параметром в `list_alerts` снято через `Query(alias="status")`.
- **Латентный circular import** `app.services ↔ app.agent` (падал при «services первым»; runtime жил только за счёт порядка импорта в main.py) — разорван TYPE_CHECKING-импортом `ResolvedModelConfig` в контрактном `app/services/agent_runner.py`. Найден точечными автотестами (теперь архивными — § Тестирование).
- **Баг на критичном пути auth (нашёл агент-тестировщик):** при replay-detect cookie-удаление терялось — `_delete_refresh_cookie` на injected `Response` + `raise HTTPException` (FastAPI строит новый ответ). Сессии ревокались, но клиентский refresh-cookie оставался. Фикс: `HTTPException(headers=_cookie_deletion_headers(...))`; верифицирован на стенде (401 несёт `Set-Cookie: refresh_token=""; Max-Age=0`). Дополнение из merge: feat-003 независимо чинил серверную половину того же бага — § Слияние.

### Инфраструктура

- `APP_PORT`/`SIEM_PORT` параметризованы в docker-compose (по образцу `POSTGRES_PORT`) — параллельные стенды в worktree больше не дерутся за 8000/8001.
- `anyio` и `httpx` объявлены явными зависимостями backend (использовались транзитивно; нужны для runtime-кода: argon2 to_thread, AsyncClient).

## Решения и развилки (согласованы с архитектором)

1. **Владение `Settings` — `app.state`, не `lru_cache`.** Унифицировано на оба сервиса. Разница с module-level синглтоном не в числе экземпляров, а во владении: `app.state` живёт с экземпляром приложения (тесты изолированы, два приложения в процессе не делят состояние), `lru_cache`/глобаль — в импортированном модуле. Прямое следствие правила «состояние в app.state».
2. **Списки в env — `Annotated[list[str], NoDecode]` + CSV-validator (пара).** Развилка из DoD разрешилась сложнее, чем «CSV vs NoDecode»: одного validator-split мало — `EnvSettingsSource` декодирует complex-тип из env как JSON **до** field-validator'а и роняет старт на CSV-строке. Поймано стендом, не юнитами (юниты конструируют `Settings(cors_origins=...)` в обход env-источника). `NoDecode` отключает раннее JSON-декодирование. Зафиксировано в conventions.md.
3. **Блокирующий код — `anyio.to_thread`, без новой зависимости.** Конвенция: async-first (если есть async-вариант библиотеки) → `def`-handler для чистого sync (FastAPI сам в threadpool) → `anyio.to_thread.run_sync` для смешанного (await + блокирующий кусок). asyncer не заводим — anyio фундамент Starlette, и feat-002 уже использовал его для pdfkit.
4. **line-length остаётся 88.** Bump до 100 отклонён: потребности нет (значение пришло из недействовавшей `[tool.ruff]`-секции pyproject, удалена как мёртвая), а bump = project-wide reformat и конфликты. Пункт в backlog.
5. **Hand-written миграции не пересоздаются** («пусть как есть») — переписывание истории миграций не оправдано.
6. **`SIEM_JWT_SECRET` обязателен + fail-fast в compose.** Dev-fallback `change-me-in-production` удалён из кода (поле без дефолта → `ValidationError`) и из compose (`${JWT_SECRET:?...}` вместо `:-fallback`). Предсказуемый JWT-секрет — дыра, которую тихий запуск маскирует. Обобщено в conventions.md § Секреты и fail-fast.
7. **`B008` включён в ruff** (ignore снят) после перевода всех handler'ов на Annotated — теперь правило страхует от возврата старого стиля.
8. **`langfuse_enabled` не трогаем** — module-level флаг с `global`, читается агентной инструментацией вне request scope (agent/runner, observer). Единственное намеренное отступление от «no module-level state»; задокументировано как исключение + кандидат на agent-slice (feat-005). Развилка по способу обработки ошибок при replay (`HTTPException(headers=)` vs явный `JSONResponse`) частично пересекается с feat-007 (error handling) — выбран минимально-инвазивный `headers=`.

## Слияние с develop

На разборе работал с устаревшим локальным ref'ом develop; после `git fetch` выяснилось, что **feat-002 (PR #65) и feat-003 (PR #66) уже влиты в develop**. Develop слит в ветку, 9 конфликтов разрешены по согласованному варианту A (моя де-синглтонизация как конечная структура + логика соседних слайсов прививается). `make check` + автотесты зелёные; merge переверифицирован независимым агентом на свежем стенде — **14/14 PASS**.

- **Replay-баг — два независимых дефекта, два слайса, один метод (прогон тест-кейсов).** feat-003 (`1fdb5f1`) починил серверную половину: ревокация откатывалась вместе с `HTTPException` (rollback в `get_db_session`) — commit до raise. feat-004 — клиентскую: cookie не удалялся. Взаимодополняющие, не дубль; на стенде проверена связка (replay → 401 + `Max-Age=0` cookie + отзыв всего семейства токенов).
- **SIEM `/events` — сохранён `admin_payload` от feat-002.** feat-002 закрыл P1 «/events без require_admin»; моя версия эндпоинта его не имела — при merge сохранил гард (иначе откатил бы security-фикс). P1-пункт убран из backlog как выполненный.
- **`patch_alert` — валидация статуса схемой (422, не 400).** feat-002 перенёс проверку в `AlertPatchRequest` (`Literal`); мою ручную 400-проверку снял. Это закрыло расхождение 8.6 из первого прогона правильным образом.
- **`correlation/engine.py` + `deduper.py`:** моя инъекция `session_factory` (без глобали) + их `_expire_stale_alerts` и атомарный upsert (ON CONFLICT). Мой параметр окна в `deduper` снят — окно ушло в `_expire_stale_alerts` движка (из инжектнутого `self._alert_open_window_seconds`).
- **`feedback.py`:** ресурс-структура feat-002 (PUT/DELETE) + мои async-фиксы. **`siem main.py`:** моя `create_app()` + их `register_problem_handlers` (RFC 9457). **`chats.py`:** recent ушёл на `Pagination` (feat-002), моя Annotated-правка `limit` снята как устаревшая. **`services/auth.py`:** авто-слияние (их replay-commit + мой argon2-to_thread).

## Тестирование

[test-cases.md](test-cases.md) — 33 ручных кейса, прогнаны независимым агентом-тестировщиком на docker-стенде (порты 8200/8201): **30 PASS, 3 SKIP** (нет LLM/Langfuse-ключей на стенде). Плюс отдельный пост-merge прогон высокориск-путей слияния — **14/14 PASS**.

**Точечные автотесты — архивированы, не в живой инфраструктуре.** По решению архитектора: писать тесты в этом слайсе было нельзя (тестовую инфраструктуру проектирует с нуля feat-009). 17 автотестов (argon2/токены, RateLimiter, CSV/NoDecode, StrEnum/`GuardResult`) своё дело сделали — поймали латентный circular import — и перенесены из `backend/tests/` в [archived-point-tests/](archived-point-tests/) как артефакт-бэкап. feat-009 проектирует тестовую рамку заново и решает, что из архива влить. Фиксы, которые они выявили (circular import), остаются в коде.

## Зафиксировано вовне (conventions / backlog)

- `doc/tech/conventions.md`: § FastAPI (владение состоянием lifespan→app.state→Depends; Annotated + type-alias; конвенция блокирующего кода; CSV+NoDecode для списков в env); § Секреты и fail-fast (секреты без рабочих дефолтов).
- Backlog добавлено/изменено: `X-Forwarded-For` доверяется безусловно (сведён в один пункт с дублем feat-002 — обход rate-лимитов + загрязнение SIEM-корреляции); дедупликация ownership `mcp_servers.py`; `POST /rules` без валидации `config` (P3); line-length 88→100; `langfuse_enabled` module-флаг.
- Backlog закрыто: P1 «SIEM /events без require_admin» (feat-002, сохранён при merge).
