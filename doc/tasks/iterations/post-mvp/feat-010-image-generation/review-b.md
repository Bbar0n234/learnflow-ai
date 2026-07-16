# Code Review — режим B (соответствие контракту): feat-010

Ревьюер: code-reviewer режим B (соответствие конвенциям, doc-first, архитектурный контракт).
Diff: `git diff develop...HEAD` (T1 backend `8ae3088`/`e5c891a`, T2 frontend `c720065`).
Base: `develop`.

## Summary

Реализация **соответствует контракту**. Blocker'ов нет. Design-brief выполнен точно по всем
зафиксированным точкам: media endpoint (форма URL, bytes из `mime_type`, 404 без блоба,
`Cache-Control: private, max-age=31536000, immutable`), таблица `artifact_blobs` (FK 1:1 CASCADE,
`bytea`, отдельный PK), «артефакт + блоб одной транзакцией» (`session.begin()` + `ArtifactRepository`
+ `PgBlobStorage` в одном скоупе), расширение SSE-маппера на имя tool'а `generate_image` без
изменения формы событий, cost в Langfuse через generation-observation с `cost_details` (fail-safe),
изображение в контекст агента не попадает (ToolMessage текстовый). Код держится существующих
прецедентов: `make_create_artifact_tool` (tool), `get_artifact` (route + ownership-guard),
`infra/llm.py` (import cycle через `TYPE_CHECKING`), `observer.py` (fail-safe suppress),
`LLMConfig.extra_body` (`params`), `SphereService`/`MCPServerRepository` (Protocol без наследования,
DI напрямую из модуля). Frontend — FSD-раскладка соблюдена, серверные данные в TanStack Query,
клиентское стрим-состояние в Zustand через селекторы, query-keys через фабрику с иерархией,
токены вместо хардкода, `console.*` нет.

Найдено: 0 blocker, 0 major, 3 nit/question (все — вкус/консистентность в рамках нормы либо
сигнал о дрейфе самой конвенции). Отдельно — **дрейф документации** (для docs-updater): новые
публичные контракты пока не отражены в `doc/tech/*`; правок doc/tech в diff нет (ожидаемо —
отдельная фаза). Плюс частный случай: конвенция § Env line 338 сама разошлась с фактическим
`env_file`-паттерном (см. ниже) — суждение T1 по `docker-compose.yml`/`.env.local.example`
**верное**, расходится текст конвенции, а не код.

## Замечания

| Severity | Намерение | Файл:строка | Норма | Замечание | Предложение |
|---|---|---|---|---|---|
| nit | Консистентность типов | `backend/app/config.py:50` | conventions.md § Типизация (консистентность формы) | `llm_image_timeout_seconds: int = 120` — соседние LLM-таймауты объявлены `float` (`llm_guard_timeout_seconds`, `llm_summarizer_timeout_seconds`). httpx принимает оба; `int`-таймауты в файле тоже есть (`mcp_*`, `pdf_*`), так что нормы это не нарушает — чистая консистентность внутри семейства `LLM_*`. | По желанию привести к `float` в тон семейству; не блокирует. |
| nit | Узкий except (мode-A граница) | `backend/app/infra/image_generation.py:91` | conventions.md § Барьерный стек (узкий except) | Кортеж `(httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError)` содержит поглощённые члены: `httpx.TimeoutException ⊂ httpx.HTTPError`, builtin `ConnectionError ⊂ OSError` (проверено рантаймом). httpx-сетевые ошибки — это `httpx.ConnectError ⊂ httpx.HTTPError`, не builtin `ConnectionError`. Except стоит на легитимном барьере трансляции в доменное исключение (как `infra/llm`), не `except Exception` — норму не нарушает; редундантность — вопрос чистоты (ближе к mode-A). | Достаточно `(httpx.HTTPError, OSError)`; остальное — подмножества. |
| question | env atomic-change (задание требовало сверить) | `backend/app/config.py`, `.env.example` (+ отсутствие правок в `docker-compose.yml`/`.env.local.example`) | conventions.md § Env line 338 vs line 315–316 | Решение T1 **не** добавлять `LLM_IMAGE_TIMEOUT_SECONDS` в `docker-compose.yml` и `.env.local.example` — **корректно** и консистентно с фактическим паттерном: сервис `app` берёт env через `env_file: [.env]` целиком, ни один `LLM_*`-таймаут в `docker-compose.yml` не перечислен; `.env.local(.example)` по конвенции (line 316) несёт только local-dev-**переопределения**, а значение 120 одинаково везде. Конфликт — с буквальным текстом line 338 («одновременное обновление … `docker-compose.yml` … Все четыре места»). Расходится **текст конвенции**, не код (см. дрейф ниже). | Оставить реализацию как есть; вынести уточнение line 338 архитектору/docs-updater. |

## Blocker без прецедента в conventions

Нет.

## Незамеченный дрейф документации (адресат — docs-updater)

Правок `doc/tech/*` в diff нет — новые публичные контракты в архитектурной документации ещё не
отражены. Точки расхождения кода и доки:

1. **`doc/tech/backend.md`** — media endpoint `GET /projects/{id}/artifacts/{aid}/media` отсутствует
   в таблице REST (строки 206–208) и в списке endpoint'ов (строки 328–335). Таблица `artifact_blobs`
   (bytea-хранилище блобов, FK 1:1 к `artifacts`) не упомянута в разделе персистентности.
2. **`doc/tech/agent-runtime.md:199`** — таблица internal tools содержит только `create_artifact`;
   `generate_image` нужно добавить (плюс упоминание секции `image` в `agent.yaml`).
3. **`doc/tech/streaming.md:24`** — `artifact_created` теперь эмитится и для `generate_image` (форма
   события не изменилась; стоит зафиксировать, что маппер срабатывает на оба имени tool'а).
4. **`doc/tech/observability.md`** — image-вызов идёт голым httpx мимо `CallbackHandler`; cost
   учитывается вручную через generation-observation с `cost_details` из `usage.cost`. Этот обходной
   путь cost-учёта не задокументирован.
5. **`doc/tech/frontend.md`** — media-fetch (`getArtifactMedia`/`useArtifactMedia`, objectURL-паттерн),
   живой `ImageViewer` вне `SHOW_GROUP_B_STUBS`, превью в `ArtifactCard`, плейсхолдер генерации
   (`GeneratingArtifactCard` на `pendingImages`/`call_id`).
6. **`doc/tech/conventions.md:338` (дрейф самой конвенции)** — правило «при добавлении env-переменной
   одновременно обновить `.env.example`, `.env.local.example`, `docker-compose.yml`, `Settings` — все
   четыре места» написано так, будто `docker-compose.yml` перечисляет каждую переменную в
   `environment:`. Фактически сервис `app` перешёл на `env_file: [.env]` и не перечисляет `LLM_*` —
   для app-переменных «четвёртое место» пустое. Текст стоит смягчить (условие «если сервис
   перечисляет переменную явно / если она — local-dev override»), иначе каждая новая app-переменная
   формально нарушает конвенцию, следуя при этом верному паттерну. Требует решения архитектора
   (изменение нормы).
