# Implementation Plan: feat-010 / трек T1 — Backend + Agent

## Контекст

Трек T1 закрывает всю бэкенд- и агентную часть генерации изображений: агент вызывает
tool `generate_image` → OpenRouter Image API → артефакт `type="image"` вместе с бинарём
в новой таблице `artifact_blobs` (одной транзакцией) → media endpoint отдаёт байты под
JWT. Впервые в системе появляются бинарные данные — это главная техническая новизна.
Frontend (живой `ImageViewer`, карточка-превью, плейсхолдер генерации) — трек T2, против
зафиксированного design-brief контракта, не против кода T1.

Источники:
- Tasklist: `doc/tasks/tasklist-post-mvp.md` § feat-010 (строки 471–494) — критерии приёмки.
- Design-brief: `doc/tasks/iterations/post-mvp/feat-010-image-generation/design-brief.md`
  — архитектура, решения, `## Партиция треков` (T1 = `backend/app/**` + миграция alembic +
  `configs/agent.yaml`; тестовый скоуп `backend/tests/**`).
- Конвенции: `doc/tech/conventions.md` + доменные `conventions/db.md` (миграции через
  autogenerate, FK с индексом), `conventions/api.md` (problem+json, list-envelope),
  `conventions/agent.md` (ReAct-топология, `StreamEventMapper`).
- Архитектурная дока: `doc/tech/backend.md`, `agent-runtime.md`, `streaming.md`,
  `observability.md`.

Референс-паттерны в коде (проверены при планировании):
- Фабрика tool'а: `backend/app/agent/tools/artifacts.py::make_create_artifact_tool`
  (замыкание над зависимостями, `@tool(response_format="content_and_artifact")`,
  `async with session_factory() as session, session.begin()`).
- Langfuse generation-observation: `backend/app/agent/security/observer.py`
  (`get_client().start_as_current_observation(as_type="generation", ...)`, fail-safe
  через `contextlib.suppress`).
- OpenRouter-доступ: `Settings.llm_api_key` / `Settings.llm_base_url`
  (`backend/app/config.py`), инфра LLM — `backend/app/infra/llm.py`.
- Wiring tool'ов: `backend/app/main.py` (~строки 334–447) — `make_create_artifact_tool`
  → `internal_tools` / `global_tools`.
- Маппер SSE: `backend/app/agent/stream_events.py` (`msg.name == "create_artifact"`).
- Регистрация моделей для autogenerate: `backend/app/models/__init__.py`
  (`__all__` + импорт), `target_metadata = Base.metadata` в `alembic/env.py`.

## Фазы

### T1.1: Модель `artifact_blobs` + миграция

**Цель:** завести таблицу под бинари — 1:1 к `artifacts`, и сгенерировать миграцию
autogenerate.

**Изменения:**
- `backend/app/models/artifact_blob.py` (новый) — модель `ArtifactBlob`: PK, FK
  `artifact_id` → `artifacts.id` (`ondelete="CASCADE"`, `index=True`, unique для 1:1),
  `mime_type: Text`, `data` — бинарная колонка (`LargeBinary` → `bytea`). Тип колонки и
  unique-constraint на FK — сверить со skill `postgresql` и `conventions/db.md`.
- `backend/app/models/artifact.py` — опциональный `relationship` к блобу (1:1); не
  тянуть блоб в дефолтный select (listing артефактов не должен грузить мегабайты).
- `backend/app/models/__init__.py` — импорт `ArtifactBlob` + запись в `__all__`
  (иначе autogenerate не увидит таблицу).
- Миграция: `make migration msg="..."` → прочитать сгенерированный файл, проверить, что
  autogenerate корректно поднял `bytea`, FK, индекс, unique.

**Verification:**
- `make check` проходит.
- Критерий приёмки: «Миграция `artifact_blobs` через autogenerate».
- Миграция применяется на чистой БД: `docker-compose down -v` → `make docker-up-db` →
  `make migrate` без ошибок; `downgrade` не роняет схему.

### T1.2: `BlobStorage` protocol + `PgBlobStorage`

**Цель:** абстрагировать доступ к блобам за `typing.Protocol`, PG-реализация
конструируется вокруг session (как репозитории).

**Изменения:**
- Новый модуль (напр. `backend/app/repositories/blob_storage.py`) — `BlobStorage`
  (`typing.Protocol`: `put`/`get`/`delete`) и `PgBlobStorage(session)` как единственная
  реализация. `put` пишет `ArtifactBlob`, `get` возвращает `(bytes, mime_type)` или
  `None`, `delete` удаляет по `artifact_id`. Сигнатуры протокола БЕЗ параметра session
  (session связывается в конструкторе — design-brief явно отклоняет `put(session, ...)`).

**Verification:**
- `make check` проходит (mypy подтверждает соответствие `PgBlobStorage` протоколу).
- Критерий приёмки: «доступ за `BlobStorage`-протоколом (PG-реализация конструируется
  вокруг session)».

### T1.3: Media endpoint

**Цель:** отдавать байты изображения под JWT с иммутабельным кэшем.

**Изменения:**
- `backend/app/api/routes/artifacts.py` — `GET
  /projects/{project_id}/artifacts/{artifact_id}/media`. Проверка принадлежности
  артефакта проекту (паттерн `get_artifact`: `artifact.project_id != project.id` → 404).
  Читает блоб через `BlobStorage.get`; нет блоба → 404. `Response(content=bytes,
  media_type=mime_type)` + заголовок `Cache-Control: private, max-age=31536000,
  immutable`.
- `backend/app/api/deps.py` — DI для `BlobStorage`/`PgBlobStorage` поверх `DBSession`
  (аналогично `get_artifact_service`), либо расширить `ArtifactService` методом доступа к
  блобу. Выбор — по месту, консистентно с существующим DI.

**Verification:**
- `make check` проходит.
- Критерий приёмки: «`GET .../media` отдаёт бинарь с корректным mime под JWT-auth и
  `Cache-Control: private, immutable`»; 404 без блоба и при чужом проекте.

### T1.4: Конфиг `image` + вызов OpenRouter Image API

**Цель:** секция `image` в `agent.yaml` и функция вызова `POST {llm_base_url}/images`
голым httpx с парсингом ответа.

**Изменения:**
- `configs/agent.yaml` — новая секция `image`: `model: google/gemini-3.1-flash-image`,
  `params: {}` (пустой словарь дефолт-параметров, прокидывается в запрос as-is —
  паттерн `extra_body`).
- `backend/app/agent/config.py` — `ImageConfig(BaseModel)` (`model: str`,
  `params: dict[str, Any] = {}`) + поле `image` в `AgentConfig` — **обязательное**
  (fail-fast: отсутствие секции в `agent.yaml` — ошибка конфигурации при старте;
  решение архитектора, см. Open Questions).
- `backend/app/config.py` — новая env-настройка `llm_image_timeout_seconds`
  (дефолт 120) для httpx-вызова генерации; синхронно обновить `.env.example`,
  `.env.local.example`, `docker-compose.yml` (atomic change по conventions.md
  § Что попадает в env; решение архитектора, см. Open Questions).
- Новый хелпер вызова OpenRouter (напр. в модуле tool'а или `backend/app/infra/`) —
  `httpx.AsyncClient` POST на `{settings.llm_base_url}/images` с
  `Authorization: Bearer {settings.llm_api_key}`, тело: `model`, `prompt`, `aspect_ratio`,
  `resolution`, `**params`. Ответ: `data[0].b64_json` (голый base64) → decode в `bytes`,
  `media_type`, `usage.cost` (USD). Non-2xx (включая 400 на невалидный параметр, 502) →
  подъём внятной ошибки БЕЗ частичной записи. Точный расход/формат `usage` — сверить
  живым вызовом при реализации (design-brief: таблицы токенов Google расходятся).

**Verification:**
- `make check` проходит.
- Критерий приёмки: «Секция `image` в `agent.yaml` (`model` + `params`), дефолт —
  `google/gemini-3.1-flash-image`».
- Живой вызов возвращает валидный `b64_json` + `media_type` + `usage.cost` (ручная
  проверка при реализации).

### T1.5: Tool `generate_image` + wiring + расширение маппера SSE

**Цель:** собрать tool по фабричному паттерну — транзакция артефакт+блоб, Langfuse
generation-observation, ToolMessage; подключить в граф; расширить SSE-маппер.

**Изменения:**
- Новый модуль `backend/app/agent/tools/image_generation.py` —
  `make_generate_image_tool(...)` по паттерну `make_create_artifact_tool`. Замыкание над
  `session_factory`, `settings` (или image-хелпером), `image_config` и флагом доступности
  Langfuse. Сигнатура tool'а: `generate_image(prompt, title, aspect_ratio?, resolution?)`,
  `response_format="content_and_artifact"`. Docstring — промптинг-блок из design-brief
  (§ «Промптинг и выбор параметров»), отредактированный под формат docstring.
  Внутри: вызвать OpenRouter (T1.4) → в одной транзакции
  (`async with session_factory() as session, session.begin()`) создать артефакт
  (`type="image"`, `content=prompt`) через `ArtifactRepository` и записать блоб через
  `PgBlobStorage(session)` → Langfuse generation-observation с `cost_details` из
  `usage.cost` (паттерн `observer.py`, fail-safe). ToolMessage: title, id, разрешение,
  стоимость; второй элемент tuple — dict артефакта (`id`, `title`, `type`) для
  `artifact_created`. Ошибка провайдера → внятная ошибка tool, транзакция не начинается.
- `backend/app/main.py` — сконструировать `generate_image` рядом с `create_artifact`,
  добавить в `internal_tools` и `global_tools`; передать флаг доступности Langfuse
  (известен по `langfuse_client`).
- `backend/app/agent/stream_events.py` — эмит `artifact_created` расширить с
  `msg.name == "create_artifact"` на `msg.name in {"create_artifact", "generate_image"}`.
  Форма события и его поля не меняются.

**Verification:**
- `make check` проходит.
- Критерий приёмки: «`generate_image(...)`: артефакт + блоб пишутся одной транзакцией,
  SSE `artifact_created` приходит (маппер расширен на `generate_image`),
  generation-observation с `cost_details` из `usage.cost` уходит в Langfuse».

## Cross-cutting

После всех фаз трека проверить:
- Все критерии приёмки T1 из tasklist (строки 484–489) закрыты.
- Миграция применяется на чистой БД: `docker-compose down -v` → `make docker-up-db` →
  `make migrate`; полный цикл `upgrade`/`downgrade` без ошибок.
- `make check` (ruff + mypy) зелёный по всему backend.
- Контракт для T2 соблюдён без отклонений: `type="image"` c `content=prompt`; media
  endpoint (`bytes`, `Content-Type` из `mime_type`, 404 без блоба, `Cache-Control:
  private, max-age=31536000, immutable`); SSE `tool_start`/`tool_end`/`artifact_created`
  без изменения формы (маппер расширен только на имя tool'а).
- Автотесты трека пишет `test-author` независимо из design-brief — на этапе планирования
  их нет; фазы верифицируются `make check` + перечисленными критериями приёмки.

## Open Questions

Нет открытых вопросов. Разрешены архитектором на эскалации оркестратора (до старта
реализации):

1. **Таймаут httpx-вызова генерации** → вариант (b): новая env-настройка
   `llm_image_timeout_seconds` (дефолт 120) в `Settings` + синхронное обновление
   `.env.example`, `.env.local.example`, `docker-compose.yml` (atomic change).
2. **Опциональность секции `image` в `AgentConfig`** → поле обязательное, fail-fast:
   отсутствие секции в `agent.yaml` — ошибка конфигурации при старте (Pydantic-валидация),
   как у остальных секций конфига.
