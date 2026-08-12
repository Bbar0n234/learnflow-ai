# Конвенции: API

Проектные решения по инфраструктуре FastAPI и REST-контрактам. Ядро — [conventions.md](../conventions.md).

## FastAPI

Проектные решения по инфраструктуре FastAPI (оба сервиса: main app + siem-service). База — skill `fastapi`; здесь только выбранные развилки и специфика репозитория.

### Владение состоянием: lifespan → app.state → Depends

Всё состояние уровня приложения создаётся в `lifespan` и живёт в `app.state`; handlers получают его через dependency, читающий `request.app.state`. Module-level синглтоны (`_instance + get_x()`, `@lru_cache`-фабрики, глобальные клиенты) запрещены жёстким правилом — `app.state` отличается от них владением: состояние привязано к экземпляру приложения (создаётся/умирает вместе с ним, в тестах каждый `create_app()` изолирован), а не к импортированному модулю.

- **lifespan** — создание/teardown ресурсов: engine, session_factory, Redis, `Settings`, `RateLimiter`, `MetaEmitter`, `JWTValidator`, фоновые задачи (`asyncio.create_task` + cancel после `yield`). Фоновым задачам глобальные переменные не нужны — локальные переменные lifespan живут через `yield`.
- **app.state** — хранение созданного; ключи именуются по объекту (`app.state.session_factory`, `app.state.meta_emitter`).
- **Depends** — доступ из handlers: тонкий getter (`def get_x(request): return request.app.state.x`) + type-alias.

`Settings()` инстанцируется один раз в `lifespan` (плюс один раз в `create_app()` для middleware-конфигурации). В handlers/dependencies — только `SettingsDep`; повторный `Settings()` на запрос — это повторный парсинг env.

### Annotated и type-alias для зависимостей

Параметры с метаданными (`Query`, `Path`, `Cookie`, `Depends`) — только в `Annotated`, дефолт остаётся обычным значением: `limit: Annotated[int, Query(ge=1, le=200)] = 50`. Переиспользуемые зависимости оборачиваются в type-alias рядом с определением (`DBSession`, `CurrentUser`, `SettingsDep` — `backend/app/api/deps.py`; `SessionDep`, `AdminPayload`, `MetaEmitterDep` — `siem_service/api/deps.py`). Правило ruff `B008` включено: вызовы в дефолтах параметров — ошибка линта, Annotated-стиль её не триггерит.

### Блокирующий код и async

Приоритет: (1) истинно асинхронный вариант, если у библиотеки он есть (`httpx.AsyncClient` вместо sync `httpx`); (2) чисто синхронный handler без await внутри — объявлять `def`, FastAPI сам уведёт его в threadpool; (3) смешанный код (await БД + блокирующий вызов) — блокирующий кусок уводить через `anyio.to_thread.run_sync` (anyio — фундамент Starlette, отдельной зависимости asyncer не заводим).

Эталонные случаи: argon2 hash/verify (`app/services/auth.py`), wkhtmltopdf (`app/api/routes/artifacts.py`), `langfuse.flush()` (`app/api/routes/feedback.py`).

### CSV для списков в env

Списочные env-значения (`CORS_ORIGINS`, `SIEM_FRONTEND_ORIGIN`) — CSV-строка, не JSON: `.env` шелл-сорсится (Makefile `LOAD_ENV`), JSON-список с кавычками такую загрузку не переживает. Реализация — **пара** `Annotated[list[str], NoDecode]` + `field_validator(mode="before")` со split: без `NoDecode` pydantic-settings декодирует complex-типы из env как JSON ещё до validator'а и падает на CSV-строке (`SettingsError` на старте).

## REST API

Проектные решения по REST-контрактам (оба сервиса: main app + siem-service). База — skill `api-design-principles`; здесь только выбранные развилки и специфика репозитория.

### Pagination и list envelope

- Пагинация — **offset/limit** (cursor не используем: коллекции — десятки-сотни элементов на пользователя). Query-параметры: `limit` (default 50, max 200), `offset` (≥0); общий dependency `Pagination` в `app/api/deps.py`.
- Envelope списочных ответов един для **всех** list-эндпоинтов, включая маленькие фиксированные списки (models, mcp-servers): `{ items, total, limit, offset }`. Generic `Page[T]` — `app/api/schemas/common.py`; endpoint-специфичные поля добавляются наследованием (пример — `inherited` в `MCPServerListResponse`).
- Решение «пагинация везде» — осознанное: не держим в голове, какой список «может вырасти», а какой нет.
- **Исключение — capability-дескриптор, не коллекция ресурсов**: `GET /api/auth/providers` (`{providers: string[], password: bool}`) вне list-envelope — санкционировано design-brief итерации feat-008. Отличие от списочных эндпоинтов: ответ описывает доступные способы входа (fixed shape, не набор идентичных ресурсов), поле `password` в `{ items, total, limit, offset }` не ложится по смыслу.

### Status codes

- `201` — POST, создающий ресурс; `204` — DELETE без тела (повторный DELETE того же ресурса — тоже `204`, идемпотентность).
- `409` — конфликт с текущим состоянием (занятый username, превышен лимит ресурсов в scope).
- `422` — ошибки валидации запроса; валидация значений выражается схемой (`Literal`, типы, constraints), а не ручными `if` + `400` в handler'е.
- **Auth-эндпоинты (`/auth/*`) — RPC-семантика**: ответ — токен-сессия, а не представление ресурса, поэтому resource-правила (201 на register, Location) на них не распространяются.
- `Location`-header на 201 не используем.

### Ошибки — RFC 9457 Problem Details

Все ошибки обоих сервисов — `application/problem+json`: `{ type, title, status, detail, …extensions }`. Реализация — глобальные handlers (`app/api/problem.py`, зеркало в `siem_service/api/problem.py`); слои перехвата (доменный / инфра / generic) — см. [Обработка ошибок → Барьерный стек](../conventions.md#обработка-ошибок).

- `type` — машинный код ошибки в форме `urn:learnflow:<code>` (пример: `urn:learnflow:security-policy-violation`); для ошибок без машинной семантики — `about:blank`, клиент ориентируется на `status`.
- `detail` — человекочитаемое сообщение; ошибки валидации несут расширение `errors` (список полей).
- В handler'ах ошибки поднимаются как обычно (`HTTPException(status, detail=...)`); структурный код передаётся dict-detail (`{"error": <code>, "message": ...}`) и конвертируется handler'ом в `type` + расширения.

### Ownership и нейминг

- Принадлежность ресурсов по path-цепочке валидируется зависимостями: `UserProject` (project → user), `UserThread` (chat → project → user). Endpoint, принимающий `{project_id}`/`{chat_id}`, обязан использовать соответствующий dependency — ручные проверки в handler'ах не пишем.
- **Граница нейминга chat/thread проходит по path**: URL-сегменты и path-параметры — `chats` / `chat_id` (user-facing язык), поля payload и внутренние слои — `thread_id` (domain язык, происходит из LangGraph).
- Action-эндпоинты (`/cancel`, `/test`, `/toggle`) допустимы как controller-паттерн для операций, не ложащихся в CRUD.

### Versioning

API не версионируется (`/api` без `v1`) до появления публичного API.
