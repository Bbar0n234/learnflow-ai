# План — T2: Устойчивость + конфигурирование (таймауты/retry через Settings/env)

Трек реализует D-ERR-9 (значения таймаутов/retry) и D-ERR-11 (все числа → `Settings`/env, не хардкод) для **обоих** сервисов (main app + siem-service). T2 **не трогает** логику обработки ошибок (барьерный стек, маппинг статусов, fail-open guard, SIEM-pipeline) — это T1/T3/T4. T2 только вводит и прокидывает таймауты/`max_retries` как операционные настройки.

Frontend axios timeout (`VITE_*`) — НЕ этот трек (T5).

## Что меняем (сводка по числам, D-ERR-9)

| Зависимость | Параметр | Значение | Сервисы |
|---|---|---|---|
| Redis | `socket_connect_timeout`, `socket_timeout` | 5s / 5s (дефолт) | main + siem |
| Postgres (app engine) | `statement_timeout` | 120s | main |
| Postgres (siem engine) | `statement_timeout` | 120s | siem |
| LangGraph checkpointer/store | `statement_timeout` + `connect_timeout` | 120s / 5s (reuse db-настройки) | main |
| MCP (все пути) | единый таймаут | 30s (`MCP_TIMEOUT` → Settings) | main |
| Guard-LLM | `timeout` | 45s | main |
| Summarizer-LLM | `timeout` | 300s (5 мин) | main |
| Все управляемые LLM | `max_retries` | 2 | main |
| Основной чат-LLM | `timeout` | **НЕ вводим** (openai-дефолт 600s) | main |

Единицы: в `Settings` храним человекочитаемые значения (секунды), конвертируем в драйвер-специфичный формат на месте использования (libpq `statement_timeout` — миллисекунды).

---

## Фаза T2.1 — Декларация всех knob'ов (Settings + env-шаблоны + compose)

**Цель.** Завести все новые env-параметры одним atomic-изменением (хард-правило «env = Settings + .env.example + .env.local.example + docker-compose.yml»). Фаза инертна: поля добавлены с дефолтами, повторяющими текущее поведение там, где оно есть; реальное использование подключают фазы T2.2–T2.6.

**Изменения по файлам.**

- `backend/app/config.py` — новые поля `Settings` (без префикса):
  - `redis_socket_timeout: float = 5.0`
  - `redis_socket_connect_timeout: float = 5.0`
  - `db_statement_timeout_seconds: int = 120`
  - `llm_guard_timeout_seconds: float = 45`
  - `llm_summarizer_timeout_seconds: float = 300`
  - `llm_max_retries: int = 2`
  - `mcp_timeout_seconds: int = 30`
  - (langgraph переиспользует `db_statement_timeout_seconds` + `redis_socket_connect_timeout`-аналог для connect — см. T2.4; отдельного поля не заводим, см. Open Question 2)
- `services/siem-service/siem_service/config.py` — новые поля `Settings` (префикс `SIEM_`):
  - `redis_socket_timeout: float = 5.0`
  - `redis_socket_connect_timeout: float = 5.0`
  - `db_statement_timeout_seconds: int = 120`
- `.env.example` — задокументировать все новые переменные (секция Application + секция SIEM): `REDIS_SOCKET_TIMEOUT`, `REDIS_SOCKET_CONNECT_TIMEOUT`, `DB_STATEMENT_TIMEOUT_SECONDS`, `LLM_GUARD_TIMEOUT_SECONDS`, `LLM_SUMMARIZER_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `MCP_TIMEOUT_SECONDS`; `SIEM_REDIS_SOCKET_TIMEOUT`, `SIEM_REDIS_SOCKET_CONNECT_TIMEOUT`, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS`. Комментарий — operational knobs, tune without rebuild.
- `.env.local.example` — **не добавляем** (следуя прецеденту файла: «только значения, отличные от .env»; существующие operational knobs `SIEM_XREAD_*`/`SIEM_POLL_*` там отсутствуют, дефолты подходят для local dev). Если архитектор хочет буквального соблюдения «всех четырёх мест» — добавить закомментированными.
- `docker-compose.yml` — в блок `siem-service.environment` добавить три проброса: `SIEM_REDIS_SOCKET_TIMEOUT: ${SIEM_REDIS_SOCKET_TIMEOUT:-5}`, `SIEM_REDIS_SOCKET_CONNECT_TIMEOUT: ${SIEM_REDIS_SOCKET_CONNECT_TIMEOUT:-5}`, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS: ${SIEM_DB_STATEMENT_TIMEOUT_SECONDS:-120}`. **App-переменные в compose НЕ дублируем**: сервис `app` использует `env_file: .env` (прецедент — `LLM_API_KEY` и др. в compose не перечислены), поэтому новые app-переменные приходят через env_file; явный проброс нужен только siem-service, у которого `environment:`-маппинг.

**Verification.** `make check` (mypy увидит новые поля); `make docker-up` / локальный старт обоих сервисов — Settings парсятся без `ValidationError`, сервисы поднимаются, `/health` зелёный.

---

## Фаза T2.2 — Redis socket-таймауты (оба сервиса)

**Цель.** Закрыть F-RES-01: `socket_timeout=None` → бесконечная блокировка рантайм-операций. Дать верхнюю границу connect и операциям.

**Изменения по файлам.**

- `backend/app/infra/redis.py` — `create_redis`: в `aioredis.from_url(...)` пробросить `socket_timeout=settings.redis_socket_timeout`, `socket_connect_timeout=settings.redis_socket_connect_timeout`. Сигнатура уже принимает `settings`.
- `services/siem-service/siem_service/main.py` — строка 51, `redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=settings.redis_socket_timeout, socket_connect_timeout=settings.redis_socket_connect_timeout)`. Startup-ping (стр. 52) автоматически попадает под connect-таймаут.

**Внимание (см. Open Question 1).** SIEM-redis-клиент из lifespan переиспользуется подписчиком (`subscriber.py`) для блокирующего `XREADGROUP block=SIEM_XREAD_BLOCK_MS` (1000ms). `socket_timeout` должен превышать block-окно, иначе блокирующее чтение упрётся в `TimeoutError`. С дефолтами 5s > 1s инвариант держится, но связь неочевидна — выношу в Open Questions.

**Verification.** Старт обоих сервисов с доступным Redis → `redis connected` без изменения поведения. Ручная проверка таймаута: указать `REDIS_URL` на недостижимый хост/порт (blackhole) → connect падает за ~5s, а не висит; в main app — graceful (`create_redis` → `None` + warning), в siem — старт падает (ping). SIEM-подписчик при штатном Redis отрабатывает цикл без спонтанных `TimeoutError` (наблюдать логи минуту).

---

## Фаза T2.3 — Postgres `statement_timeout` (оба engine)

**Цель.** Закрыть F-RES-02: запрос может висеть бесконечно. Поставить верхнюю границу на **отдельный SQL** (не на turn агента).

**Изменения по файлам.**

- `backend/app/infra/db.py` — `create_engine`: добавить `connect_args` для драйвера **psycopg3** (URL `postgresql+psycopg`): `connect_args={"options": f"-c statement_timeout={settings.db_statement_timeout_seconds * 1000}"}`. Сохранить `pool_pre_ping=True`, `echo=False`.
- `services/siem-service/siem_service/infra/db.py` — `create_engine`: добавить `connect_args` для драйвера **asyncpg** (URL `postgresql+asyncpg`): `connect_args={"server_settings": {"statement_timeout": str(settings.db_statement_timeout_seconds * 1000)}}`. Драйвер-специфика: asyncpg не принимает libpq `options`, только `server_settings`-dict.

**Критический verification-пункт (из decisions.md, закрытые микро-вопросы).** Подтвердить, что `statement_timeout` не убивает turn агента. **Findings планировщика:** `statement_timeout` в Postgres измеряет время *одного SQL-statement*, а не транзакции. `chat.py` держит request-scoped сессию поверх стрима агента (рано коммитит на стр. 55), `create_artifact` использует отдельный `session_factory`. Открытая транзакция вокруг LLM-вызова turn НЕ убивается `statement_timeout` — его убил бы только `idle_in_transaction_session_timeout`, который мы **намеренно НЕ вводим**. Вывод: 120s на отдельный SQL безопасно. **Жёсткое требование трека: НЕ добавлять `idle_in_transaction_session_timeout`** (это превратило бы statement-timeout в turn-timeout).

**Verification.** `SHOW statement_timeout` на сессии каждого сервиса → `120000` (ms). Ручной таймаут: выполнить `SELECT pg_sleep(130)` через сессию приложения → отмена на 120s с ошибкой statement timeout (мапится в 504/503 — но маппинг это T1, здесь проверяем только что таймаут срабатывает). Прогон обычного chat-turn длиннее 120s (reasoning-модель) → turn НЕ прерывается (подтверждает per-statement семантику).

---

## Фаза T2.4 — LangGraph checkpointer/store таймауты

**Цель.** Закрыть F-RES-03: checkpointer/store дёргаются на каждом шаге графа без таймаута.

**Findings планировщика (ограничение API).** `AsyncPostgresSaver.from_conn_string(conn_string, *, pipeline, serde)` — connection-kwargs/pool_config **не принимает**; `AsyncPostgresStore.from_conn_string(..., pool_config=...)` принимает `pool_config`, но saver — нет. Единый рычаг, работающий для обоих, — параметры подключения в самой строке URL (libpq): `statement_timeout` через `options`, плюс `connect_timeout`.

**Изменения по файлам.**

- `backend/app/config.py` — расширить property `langgraph_database_url`: к плейн-URL добавить query-параметры `options=-c%20statement_timeout%3D<ms>` и `connect_timeout=<sec>`, значения из `db_statement_timeout_seconds` и (для connect) фиксированно/из `redis_socket_connect_timeout`-аналога — **уточнить источник connect-таймаута в Open Question 2**. URL-кодирование пробела/`=` в `options` обязательно.
- `backend/app/infra/langgraph.py` — без изменений сигнатур (получает уже обогащённый `db_url`); либо, если архитектор предпочтёт явность, передавать таймаут отдельным аргументом. Рекомендация: обогащать URL в config (одно место).

**Verification.** Старт main app → `store.setup()` / `checkpointer.setup()` проходят; chat-turn использует граф (запись checkpoint) без ошибок. На соединении langgraph-пула `SHOW statement_timeout` → `120000`. Проверить, что URL-кодирование корректно (psycopg парсит `options` без ошибки connect).

---

## Фаза T2.5 — LLM-таймауты и `max_retries`

**Цель.** Закрыть F-RES-04 для управляемых нами LLM: guard 45s, summarizer 300s, `max_retries=2` для всех; основной чат — без таймаута (оставляем openai-дефолт).

**Изменения по файлам.**

- `backend/app/infra/llm.py`:
  - `_build_chat_model(...)` — добавить опциональные параметры `timeout: float | None = None`, `max_retries: int | None = None`; класть в `kwargs` (`timeout`, `max_retries`) только если не `None` (паттерн как у `max_tokens`/`temperature`). `ChatOpenAI` принимает оба.
  - `create_guard_llm` — передать `timeout=settings.llm_guard_timeout_seconds`, `max_retries=settings.llm_max_retries`.
  - `create_summarization_llm` — `timeout=settings.llm_summarizer_timeout_seconds`, `max_retries=settings.llm_max_retries`.
  - `create_llm_from_config` (основной чат) — `max_retries=settings.llm_max_retries`, **без** `timeout` (D-ERR-9: чат не трогаем).

**Не путать.** `LLMClassifierConfig.max_retries` (`security/types.py:121`, дефолт 3) — это bounded-цикл ретраев на **невалидный вывод** классификатора, а не openai-`max_retries` транзиентных сбоев. Это бизнес-инвариант агента, остаётся в agent-config, T2 его НЕ трогает. Новый `llm_max_retries` (Settings) — отдельная операционная настройка openai-клиента.

**Решение «Settings vs agent-config» (по конвенции «операционное → Settings»).** Таймауты/`max_retries` — операционные ручки → `Settings` (соответствует D-ERR-11, где они перечислены как env). Имя модели и `extra_body` остаются в agent-config (идентичность/поведение модели). Так и делаем.

**Verification.** `make check`. Юнит-уровень (кандидат в автотесты): сконструировать guard/summarizer/chat LLM и проверить, что `ChatOpenAI` получил `request_timeout`/`max_retries` (через атрибуты модели или мок конструктора). Live-таймаут LLM воспроизводится тяжело — основная страховка автотестом на проброс kwargs.

---

## Фаза T2.6 — MCP единый таймаут (промоция константы в Settings)

**Цель.** Закрыть F-RES-06 и устранить рассинхрон: `MCP_TIMEOUT=30` (константа в `mcp_tool_resolver.py:22`) и хардкод `30` в `mcp_server.py`, `routes/mcp_servers.py`, плюс **отсутствие** таймаута в `infra/mcp.py`. Единый источник — `settings.mcp_timeout_seconds`.

**Изменения по файлам (прокидка значения; конструкторы/функции получают таймаут, не читают глобал).**

- `backend/app/services/mcp_tool_resolver.py` — удалить `MCP_TIMEOUT = 30`; в `MCPToolResolver.__init__` добавить параметр `mcp_timeout: int`, хранить в `self._mcp_timeout`, использовать в `SSEConnection(... sse_read_timeout=self._mcp_timeout)` и `StreamableHttpConnection(... timeout=self._mcp_timeout)` (стр. 153, 161).
- `backend/app/services/mcp_server.py` — `_build_test_connection(url, transport, api_key, timeout)` и `fetch_remote_metadata(url, transport, api_key, timeout)` — добавить параметр `timeout`, заменить хардкод `30`. `MCPServerService` (`__init__`, стр. 154) получает `mcp_timeout` и передаёт в вызов `fetch_remote_metadata` (стр. 268).
- `backend/app/api/routes/mcp_servers.py` — `_test_connection(url, transport, api_key, timeout)` — параметр `timeout`, заменить два хардкода `30` (стр. 116, 123). Хендлеры, вызывающие `_test_connection` (`test_user_server`/`test_project_server`/`test_thread_server`) и `_build_mcp_service`, берут значение из `request.app.state.settings.mcp_timeout_seconds` (паттерн app.state-ownership; `request` у хендлеров уже есть).
- `backend/app/infra/mcp.py` — `_build_connection`, `build_mcp_connections`, `create_mcp_client` — добавить параметр `timeout`; в `SSEConnection`/`StreamableHttpConnection` проставить `sse_read_timeout`/`timeout` (сейчас отсутствуют — это и есть F-RES-06).
- `backend/app/main.py` — прокинуть `settings.mcp_timeout_seconds` в: `create_mcp_client(active_mcp, timeout=...)` (стр. 399), `fetch_remote_metadata(...)` внутри `_validate_builtin_mcp` (стр. 124), конструктор `MCPToolResolver(...)` (стр. 445), и в `_build_mcp_service` (через `request.app.state.settings`). `_validate_builtin_mcp` принимает `settings`/`timeout` как аргумент.

**Verification.** `make check` (mypy/ruff — особенно `PLC0415`-импорты не затрагиваем). Ручная: `POST .../mcp-servers/test` на заведомо недостижимый URL → ответ возвращается за ~30s (`TestConnectionResponse(success=False)`), не висит. Кандидат в автотесты: `build_mcp_connections(..., timeout=7)` проставляет `sse_read_timeout=7`/`timeout=7` в connection-dict.

---

## Подход к verification (общий; тест-фаза — отдельно, позже)

Тестовая философия проекта (conventions § Тестирование): системную тест-инфраструктуру строит feat-009; здесь страховка — **ручные тест-кейсы** (документ + прогон агентом-тестировщиком) плюс точечные автотесты, которые архивируются в артефакты итерации, а не оседают в `backend/tests/`.

1. **Статика — после каждой фазы.** `make check` (ruff + mypy) для backend. Frontend трека нет.
2. **Старт обоих сервисов.** `make docker-up` (или local dev) — оба сервиса поднимаются, `/health` зелёный, Settings парсятся без `ValidationError`. Это проверяет T2.1–T2.6 в связке (env прокинуты, engine/redis/llm/mcp строятся).
3. **Ручные таймаут-проверки (по фазам).**
   - Redis: blackhole-URL → connect падает за `socket_connect_timeout`, не висит (main → graceful None; siem → fail-fast на ping).
   - Postgres: `SHOW statement_timeout` = 120000 на обоих; `SELECT pg_sleep(130)` отменяется на 120s; длинный chat-turn НЕ прерывается.
   - LangGraph: `SHOW statement_timeout` на langgraph-пуле = 120000; chat-turn пишет checkpoint без ошибок.
   - MCP: test-connection на недостижимый URL возвращается за ~`mcp_timeout`.
4. **Кандидаты в автотесты (архив итерации).**
   - `Settings`/`SIEM Settings` — дефолты новых полей и парсинг из env.
   - `_build_chat_model` прокидывает `timeout`/`max_retries` в `ChatOpenAI` (guard/summarizer/chat-варианты).
   - `create_engine` (оба) формирует `connect_args` с `statement_timeout` (драйвер-специфично).
   - `langgraph_database_url` корректно URL-кодирует `options`.
   - `build_mcp_connections` / `MCPToolResolver` / `fetch_remote_metadata` проставляют единый таймаут.
5. **Регрессия по turn-семантике (критично, из decisions).** Подтвердить per-statement природу `statement_timeout` и отсутствие `idle_in_transaction_session_timeout` (см. T2.3) — не дать таймауту убивать длинные reasoning-turn'ы.

---

## Файлы трека

Точный список путей (для карты пересечений):

- `backend/app/config.py`
- `backend/app/infra/redis.py`
- `backend/app/infra/db.py`
- `backend/app/infra/langgraph.py`
- `backend/app/infra/llm.py`
- `backend/app/infra/mcp.py`
- `backend/app/services/mcp_tool_resolver.py`
- `backend/app/services/mcp_server.py`
- `backend/app/api/routes/mcp_servers.py`
- `backend/app/main.py`
- `services/siem-service/siem_service/config.py`
- `services/siem-service/siem_service/infra/db.py`
- `services/siem-service/siem_service/main.py`
- `.env.example`
- `docker-compose.yml`
- (`.env.local.example` — только если архитектор требует буквального соблюдения правила «четырёх мест»; по умолчанию НЕ трогаем — см. T2.1)

## Пересечения с другими треками (для карты)

- **`backend/app/main.py`** — ВЫСОКИЙ риск. T2 правит прокидку MCP-таймаута (construct `MCPToolResolver`, `create_mcp_client`, `_validate_builtin_mcp`). T1/T3 (рефактор путь B→A, барьерный стек, exception-handlers) почти наверняка тоже правят main.py. Нужна координация по очерёдности/merge.
- **`backend/app/services/mcp_server.py`** и **`backend/app/api/routes/mcp_servers.py`** — ВЫСОКИЙ риск. T2 добавляет timeout-параметры; T1/T3 переводят прямые `raise HTTPException` (mcp_server.py импортирует `HTTPException`) на доменные `AppError` (D-ERR-1 явно называет mcp-путь). Те же функции/хендлеры. Сильная координация.
- **`services/siem-service/siem_service/main.py`** — СРЕДНИЙ риск. T2 правит `redis.from_url` (socket-таймауты). T4 (SIEM-pipeline, D-ERR-7) может править siem main.py / lifespan / subscriber wiring. Пересечение по lifespan.
- **`backend/app/config.py`** — СРЕДНИЙ риск. T2 добавляет timeout/retry-поля. Любой трек, добавляющий env (например error-messages-конфиг), тоже сюда. Конфликт на уровне соседних строк, мерджится, но координировать.
- **`docker-compose.yml`** / **`.env.example`** — НИЗКИЙ-СРЕДНИЙ. T2 добавляет siem timeout-env. T5 (frontend axios `VITE_*`) тоже добавит env в `.env.example` (другая секция). Возможен конфликт по соседним строкам.
- **`backend/app/infra/{redis,db,langgraph,llm,mcp}.py`, `siem .../infra/db.py`** — НИЗКИЙ риск. Инфра-конструкторы — почти эксклюзивно T2.

## Open Questions

1. **SIEM Redis `socket_timeout` vs блокирующий `XREADGROUP`.** Lifespan-клиент siem (`main.py:51`) переиспользуется подписчиком для блокирующего чтения `block=SIEM_XREAD_BLOCK_MS` (1000ms). `socket_timeout` обязан превышать block-окно, иначе блокирующие чтения будут падать в `TimeoutError`. С дефолтами 5s > 1s инвариант держится, но: (а) подтвердить дефолт `SIEM_REDIS_SOCKET_TIMEOUT=5` и зафиксировать инвариант `socket_timeout > xread_block_ms` (валидатор в Settings?); или (б) выделить отдельный Redis-клиент для блокирующего подписчика (без/с большим socket_timeout), а socket-таймаут применять только к остальным операциям. Решение архитектора — это связь, не покрытая D-ERR-9.

2. **Источник connect-таймаута для LangGraph URL и единый vs раздельный statement_timeout.** (а) `from_conn_string` не принимает connection-kwargs (saver) → таймауты инжектируем через libpq-параметры в `langgraph_database_url` (`options=-c statement_timeout=...`, `connect_timeout=...`). Подтвердить этот механизм как приемлемый (vs. отказ от connect-таймаута для langgraph). (б) Откуда брать `connect_timeout` для langgraph — завести отдельное поле или переиспользовать значение? (в) Переиспользовать `db_statement_timeout_seconds` (120s) и для основного engine, и для langgraph (рекомендация — да, один knob), или развести в два поля? Saver не имеет рычага pool-checkout-таймаута — принять этот gap?
