# Implementation Plan: feat-012 / трек T1 — Backend: skill-scoped user context

## Контекст

Трек T1 реализует бэкенд-механизм per-user контекста, привязанного к скиллу: четвёртый namespace в LangGraph Store `("user", uid, "skill_context", <skill>)`, доменные агентские tools, дозагрузку индекса контекста при `load_skill`, REST CRUD `/users/me/skill-contexts` с security-checkpoint и бизнес-лимитами. Первый потребитель — профиль авторского голоса `tech-article-writing` (данные появятся естественным путём, миграция не нужна).

Источники:
- Tasklist: `doc/tasks/tasklist-post-mvp.md` § feat-012 (строки 525–547) — цель, критерии приёмки.
- Design-brief: `doc/tasks/iterations/post-mvp/feat-012-skill-context/design-brief.md` — модель хранения, доставка через `load_skill`, tools, REST/безопасность, лимиты, `## Партиция треков` (границы T1 — строки 105–118).
- ADR-015 (`doc/tech/adr/ADR-015-unified-memory-backend.md`) — Store как unified memory backend, единый паттерн расширения через namespace.
- `doc/tech/agent-runtime.md`, `doc/tech/user-memory.md` — устройство runtime и слоёв памяти.
- Доменные конвенции: `doc/tech/conventions/{agent,api,db,testing}.md`.

Код-прецеденты (образцы, не переписывать): tools — `backend/app/agent/tools/user_memory.py`, `store_helpers.py`, `skills.py`; сервис + checkpoint на записи — `backend/app/services/user_memory.py` (`CUSTOM_INSTRUCTIONS_WRITE`) и `backend/app/services/sphere.py` (`KS_WRITE_REST`); REST — `backend/app/api/routes/user_memory.py`, `backend/app/api/schemas/user_memory.py`; checkpoint-инфраструктура — `backend/app/agent/security/types.py`, `configs/security.yaml`, `backend/app/agent/security/detectors/{canary,unicode}.py`.

**Границы T1 (из `## Партиция треков`):** только `backend/**`. Frontend (T2) работает от REST-контракта, зафиксированного в design-brief, не от кода T1. Внутритрековые общие файлы за T1: `backend/app/main.py`, `backend/app/api/routes/__init__.py`, `backend/app/agent/tools/__init__.py`, `backend/app/agent/security/types.py`, `backend/tests/conftest.py`. **doc/** трек не трогает** (кроме `tracks/T1/`) — актуализация доков идёт фазой DOC_UPDATE после барьера; замеченный дрейф фиксируется строкой в summary трека.

**Автотесты пишет отдельный `test-author`** (автономно из design-brief) — фазы ниже их не создают. Verification опирается на `make check` и критерии приёмки; проверка поведения тестами — вне этого плана.

### Ключевые архитектурные факты (верифицированы по коду/пакету)

- LangGraph Store: namespace — `tuple[str, ...]` произвольной длины (проверено `inspect` в `.venv`), четырёхэлементный namespace валиден. `asearch(prefix)` матчит по префиксу: `asearch(("user", uid, "skill_context"))` вернёт документы по **всем** скиллам пользователя; `asearch(("user", uid, "skill_context", skill))` — по одному скиллу. `asearch` limit по умолчанию 10 — при листинге поднять явно (верхняя граница ≤ 20 скиллов × 20 документов).
- `SecurityPolicyViolationError` (`backend/app/services/exceptions.py`) — `AppError` со `status = 422`; `NotFoundError` — 404. Глобальный `AppError`-handler (`backend/app/api/problem.py`) маппит их в problem+json автоматически — route try/except не нужен (прецедент: `sphere`/`user_memory` роуты бросают из сервиса).
- Индекс скиллов сейчас собирается на старте как форматированная строка (`scan_skills_index`, `main.py:334`); множества имён скиллов в `app.state` пока нет — его нужно добавить (см. T1.1).

## Фазы

### T1.1: Реестр имён скиллов + агентские tools `get/save/delete_skill_context`

**Цель:** дать агенту доменные инструменты чтения/upsert/удаления документов контекста скилла с изоляцией по `user_id`+`skill_name`, лимитами и проверкой существования скилла в библиотеке.

**Изменения:**
- `backend/app/agent/tools/skills.py` — добавить startup-хелпер, возвращающий множество имён скиллов библиотеки (например `scan_skill_names(skills_dir) -> frozenset[str]`), по логике `_list_available` (директория со `SKILL.md`). Это единый источник «библиотеки» и для tool-проверки, и для REST-флага `in_library`.
- `backend/app/agent/tools/skill_context.py` (новый) — фабрика `make_skill_context_tools(...)`, возвращающая `[get_skill_context, save_skill_context, delete_skill_context]`. Store и `user_id` берутся из `ToolRuntime` (образец `user_memory.py`); множество имён скиллов — из замыкания фабрики. Namespace `("user", uid, "skill_context", skill_name)`, value `{"description", "content"}`.
  - `save_skill_context(skill_name, key, description, content)` — upsert. Проверки (возврат error-строкой, как принято у tools; исключения не бросаем): формат `skill_name` (по `_SKILL_NAME_RE`), существование скилла в реестре (несуществующее/опечатанное имя → отказ, осиротевшие namespace не создаются), лимиты — `content` ≤ 20 000, `description` ≤ 200; документов на скилл ≤ 20 **только при создании нового key** (посчитать существующие через `asearch` по namespace скилла; upsert существующего лимитом числа не ограничен). **Add-time security-checkpoint в tool НЕ добавляем** — аргументы уже покрыты runtime-checkpoint `tool_call_arg` (design-brief § Инструменты).
  - `get_skill_context(skill_name, key)` / `delete_skill_context(skill_name, key)` — `aget`/`adelete` по namespace.
- `backend/app/agent/tools/__init__.py` — экспортировать фабрику (и `scan_skill_names`), собрать список `skill_context_tools` по образцу `user_memory_tools`.
- `backend/app/main.py` — собрать реестр имён на старте, положить в `app.state` (для REST); создать skill-context tools через фабрику и включить их в `internal_tools` и `global_tools` (обе точки: строки ~343 и ~430).

**Verification:**
- `make check` проходит.
- Критерий приёмки: tools `get/save/delete_skill_context` существуют, изолированы по `user_id` и `skill_name` (namespace содержит оба); зарегистрированы в обоих списках инструментов (`internal_tools` для security-corpus, `global_tools` для графа).
- `save_skill_context` под несуществующее имя скилла отклоняется; лимиты (20 000 / 200 / 20 документов) применяются как заявлено.

### T1.2: Дозагрузка индекса контекста в `load_skill`

**Цель:** при `load_skill(skill_name)` (без `file`) дописывать индекс документов контекста пользователя для этого скилла — только `key: description`, только при непустом namespace.

**Изменения:**
- `backend/app/agent/tools/skills.py` — `make_load_skill_tool` дополнить доступом к Store и `user_id` через `ToolRuntime` (добавить параметр `runtime: ToolRuntime` в инструмент `load_skill`; он инъектируется, для модели невидим — как в `user_memory`). Чтение файлов скилла оставить в `asyncio.to_thread` (`_load_skill_sync`), а `asearch(("user", uid, "skill_context", skill_name))` выполнить в async-обёртке и приклеить секцию индекса к результату **только когда** `file is None`, скилл найден и документы есть. Формат строки индекса — `key: description` (переиспользовать `store_helpers.format_index` или аналогичный формат). Пустой namespace → секция не дописывается, вывод `load_skill` не меняется.
- `backend/app/main.py` — при необходимости скорректировать создание `load_skill` (сигнатура фабрики), не меняя место регистрации.

**Verification:**
- `make check` проходит.
- Критерий приёмки: `load_skill` дописывает индекс контекста (только `key` + `description`) для загружаемого скилла; при пустом namespace выдача не меняется; содержимое документов при `load_skill` не грузится (только индекс — двухуровневый progressive disclosure).

### T1.3: Новый security-checkpoint `SKILL_CONTEXT_WRITE`

**Цель:** ввести checkpoint для REST-записи контекста скилла (точка персистентной инъекции — контент инжектится агенту в будущих сессиях), по образцу `CUSTOM_INSTRUCTIONS_WRITE`.

**Изменения:**
- `backend/app/agent/security/types.py` — добавить `SKILL_CONTEXT_WRITE = "skill_context_write"` в `Checkpoint`; в `_DIRECTION_MAP` — `Direction.INBOUND`.
- `backend/app/agent/security/detectors/canary.py` и `detectors/unicode.py` — добавить новый checkpoint в `applies_to` (симметрично `CUSTOM_INSTRUCTIONS_WRITE` / `KS_WRITE_REST`).
- `configs/security.yaml` — добавить блок checkpoint `skill_context_write` (`classifier_enabled: true`, `description` + `specifics`) по образцу `custom_instructions_write`/`ks_write_rest`: контент оценивается так, как будто уже инжектирован агенту как доверенный per-user контекст; INJECTION при override/role-switch/раскрытии системного промпта и т.п., легитимная персонализация — CLEAN. (См. Open Questions — файл вне `backend/app/**`.)

**Verification:**
- `make check` проходит.
- Checkpoint резолвится через `checkpoint_configs(security_config)`; детекторы `canary`/`unicode` применяются к нему.

### T1.4: Сервис + Pydantic-схемы REST

**Цель:** сервисный слой над Store для skill-context и схемы запросов/ответов REST по прецеденту `user_memory`.

**Изменения:**
- `backend/app/api/schemas/skill_context.py` (новый) — модели ответов/запроса (snake_case, даты ISO, **без конверта пагинации**): документ (`key`, `description`, `content`, `created_at`, `updated_at`); группа скилла (`skill_name`, `in_library`, `documents: [...]`); листинг (`{ "skills": [...] }`); тело PUT (`description`, `content` — оба обязательны, `Field(max_length=...)`: `content` ≤ 20 000, `description` ≤ 200). Формы тел — строго по design-brief § REST API (строки 67–74).
- `backend/app/services/skill_context.py` (новый) — `LangGraphSkillContextService(store, guard, skill_names)` + data-dataclasses. Методы:
  - `list_skill_contexts(user_id)` — `asearch(("user", uid, "skill_context"))` (limit с запасом), группировка по 4-му элементу namespace (`skill_name`), флаг `in_library` из реестра имён; полные документы в листинге.
  - `get_document(user_id, skill_name, key)` — `aget`; отсутствует → `NotFoundError` (→404).
  - `update_document(user_id, skill_name, key, description, content)` — **PUT правит только существующий документ**: сначала проверка существования (`aget`; нет → `NotFoundError` 404), **затем** guard `SKILL_CONTEXT_WRITE` (INJECTION → `SecurityPolicyViolationError` 422; classifier не гоняется по заведомо отклонённому 404-запросу), затем `aput` полной заменой value. Логирование security-события — по образцу `user_memory.update_instructions` (`security_event=True`, checkpoint, verdict, identifiers).
  - `delete_document(user_id, skill_name, key)` — существование (нет → `NotFoundError` 404), затем `adelete`.
  Порядок проверок на PUT (404 → checkpoint) — строго по design-brief (строка 76).

**Verification:**
- `make check` проходит.
- Лимиты симметричны tools (Pydantic на REST); порядок проверок PUT (404 перед checkpoint) соблюдён; создание через REST не предусмотрено (только PUT существующего).

### T1.5: REST-роуты `/users/me/skill-contexts` + wiring

**Цель:** поднять четыре эндпоинта поверх сервиса и подключить роутер.

**Изменения:**
- `backend/app/api/routes/skill_context.py` (новый) — `APIRouter`, сервис строится из `request.app.state` (`store`, `security_guard`, реестр имён скиллов) по образцу `_get_memory_service`. Эндпоинты (аутентификация через `CurrentUser`):
  - `GET /users/me/skill-contexts` → группировка по скиллам с `in_library`.
  - `GET /users/me/skill-contexts/{skill_name}/{key}` → объект документа / 404.
  - `PUT /users/me/skill-contexts/{skill_name}/{key}` → объект документа; 404 (нет пары) / 422 (INJECTION) / 200.
  - `DELETE /users/me/skill-contexts/{skill_name}/{key}` → 204 / 404.
  Route try/except не нужен — `NotFoundError`/`SecurityPolicyViolationError` маппятся глобальным `AppError`-handler.
- `backend/app/api/routes/__init__.py` — добавить модуль в импорт и `__all__`.
- `backend/app/main.py` — `app.include_router(skill_context.router, prefix=api_prefix)` (рядом с прочими, ~строка 597+).

**Verification:**
- `make check` проходит.
- REST-контракт соответствует design-brief § REST API: пути, методы, коды (200/404/422/204), формы тел (snake_case, ISO-даты, без пагинации, `in_library` на группе).

## Cross-cutting

После всех фаз трека проверить против критериев приёмки feat-012 (tasklist строки 538–542) и design-brief:

- Изоляция по `user_id` и `skill_name` сквозная (namespace-ключ) — tools и REST.
- `load_skill` дописывает индекс (только `key` + `description`) загружаемого скилла; пустой namespace → без изменений выдачи; содержимое документов — только tool'ом `get_skill_context`.
- REST CRUD работает; PUT проходит новый checkpoint `SKILL_CONTEXT_WRITE` (INJECTION → 422); создание через REST отсутствует; порядок 404→checkpoint соблюдён.
- Данные переживают удаление скилла из библиотеки (хранение в Store развязано с наличием скилла): документы остаются, доступны через REST с бейджем `in_library=false`; доставка в модель прекращается (нет скилла → некому вызвать `load_skill`).
- Симметрия путей записи: создание — только агент (`save_skill_context`), правка — агент + REST, удаление — агент + REST.
- Бизнес-лимиты (20 000 / 200 / ≤ 20 документов) применяются одинаково в tools и на REST.
- `make check` (ruff + mypy) зелёный; module-level синглтоны отсутствуют (реестр и сервисы — через `app.state`/DI, замыкания фабрик).

Автотесты (`backend/tests/skill_context/`) пишет `test-author` из design-brief — в этом плане не создаются, но покрывают перечисленные критерии.

## Open Questions

1. **`configs/security.yaml` вне файлового скоупа T1.** Столбец «Файловый скоуп» партиции треков перечисляет `backend/app/**` и `backend/tests/skill_context/`; `configs/security.yaml` (корень репозитория) в него буквально не входит. При этом добавление checkpoint без блока в `security.yaml` невозможно (прецеденты `custom_instructions_write`/`ks_write_rest` живут именно там), файл сугубо бэкендовый и с T2 (frontend-only) не пересекается. Трактую правку как внутритрековую необходимость T1 и фиксирую для подтверждения архитектором, чтобы не расширять скоуп молча. Разрешение по умолчанию: включить в T1.3; если архитектор против — вынести конфиг-правку в отдельный instructed-шаг.

2. **Источник проверки существования скилла: startup-снимок vs live-FS.** Реестр имён (T1.1) собирается на старте, как и `scan_skills_index`; `save_skill_context` и REST `in_library` сверяются с этим снимком. `load_skill`, напротив, проверяет файловую систему вживую (существующее поведение). Итог — единый источник «библиотеки» для нового функционала (снимок), при сохранении текущей live-проверки `load_skill`. Расхождение возможно только если скилл добавлен/удалён без рестарта; на текущем масштабе считаю приемлемым и соответствующим design-brief («индекс скиллов, собранный на старте приложения»). Если архитектор хочет единый механизм и для `load_skill` — это отдельное решение вне scope T1.
