# Тест-кейсы — T2: Таймауты/retry через Settings/env

Ручные тест-кейсы на **целевое** поведение трека T2 (D-ERR-9 + D-ERR-11). Автотест-инфраструктура — feat-009; здесь точечные автотесты помечены как кандидаты, остальное — ручной прогон. Кейсы, требующие LLM-ключа или нагрузочной симуляции, помечены `👤`.

Слои:
- **Layer 0** — статика и старт: `make check` зелёный; сервисы поднимаются с новыми env; осмысленное падение при некорректных значениях.
- **Layer 1** — конфигурация: значения читаются из Settings/env (не хардкод); инвариант `socket_timeout > xread_block`; env заведены во всех обязательных местах.
- **Layer 2** — поведение: быстрый отказ на недоступной зависимости, statement_timeout рубит долгий SQL, длинный agent-turn НЕ рубится.

Справочные дефолты (D-ERR-9): Redis socket/connect = 5s/5s; Postgres `statement_timeout` = 120s (оба engine); LangGraph reuse 120s + connect 5s; MCP = 30s; guard-LLM = 45s; summarizer-LLM = 300s; `max_retries` = 2; основной чат-LLM timeout НЕ вводим. SIEM `xread_block_ms` = 1000.

---

## Layer 0 — статика и старт

**{T2.1}** · Layer 0 · Предусловие: ветка трека, все фазы T2.1–T2.6 применены.
Шаги: из корня репозитория выполнить `make check`.
Ожидаемо: ruff + mypy проходят без ошибок; mypy видит новые поля `Settings` (типы `float`/`int`); `PLC0415` (локальные импорты) не нарушен — таймаут-параметры не вводят ленивых импортов.

**{T2.2}** · Layer 0 · Предусловие: доступны Postgres и Redis (`make docker-up-db`), валидный `.env` со всеми обязательными секретами.
Шаги: поднять main app (`make dev` либо `make docker-up`); дождаться старта; запросить `/health`.
Ожидаемо: сервис стартует без `ValidationError`; `Settings` парсятся (новые поля берут дефолты); `/health` зелёный; в логах `redis connected`, engine/langgraph инициализированы.

**{T2.3}** · Layer 0 · Предусловие: те же зависимости доступны.
Шаги: поднять siem-service; запросить его `/health`.
Ожидаемо: сервис стартует без `ValidationError`; новые `SIEM_*`-поля парсятся; `/health` зелёный; `redis connected`, subscriber и correlation-задачи запущены.

**{T2.4}** · Layer 0 · Предусловие: main app, переопределить `REDIS_SOCKET_TIMEOUT=abc` (нечисловое).
Шаги: попытаться стартовать сервис с этим env.
Ожидаемо: старт падает осмысленным `ValidationError` от pydantic (поле `redis_socket_timeout`, ожидался float), а не тихо игнорирует/подставляет дефолт. То же ожидается для `DB_STATEMENT_TIMEOUT_SECONDS=foo`, `LLM_MAX_RETRIES=1.5`. Кандидат в автотест (parametrize по полям).

**{T2.5}** · Layer 0 · Предусловие: siem-service, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS=notanumber`.
Шаги: попытаться стартовать.
Ожидаемо: `ValidationError` на старте siem с указанием поля; сервис не поднимается. Кандидат в автотест.

---

## Layer 1 — конфигурация (Settings/env, не хардкод)

**{T2.6}** · Layer 1 · Предусловие: код config обоих сервисов.
Шаги: проверить наличие полей в `backend/app/config.py`: `redis_socket_timeout`, `redis_socket_connect_timeout`, `db_statement_timeout_seconds`, `llm_guard_timeout_seconds`, `llm_summarizer_timeout_seconds`, `llm_max_retries`, `mcp_timeout_seconds`; в `services/siem-service/siem_service/config.py`: `redis_socket_timeout`, `redis_socket_connect_timeout`, `db_statement_timeout_seconds`.
Ожидаемо: все поля присутствуют с дефолтами из D-ERR-9 (5.0/5.0/120/45/300/2/30; siem 5.0/5.0/120). Кандидат в автотест: инстанцировать `Settings()` без env → проверить дефолты.

**{T2.7}** · Layer 1 · Предусловие: возможность переопределить env.
Шаги: стартовать main app с `MCP_TIMEOUT_SECONDS=7`, `DB_STATEMENT_TIMEOUT_SECONDS=200`, `LLM_GUARD_TIMEOUT_SECONDS=60`; прочитать значения из `app.state.settings` (или лог).
Ожидаемо: `Settings` отражают переданные значения (7/200/60), а не дефолты — подтверждает чтение из env. Кандидат в автотест (`Settings(_env_file=None)` с monkeypatch env).

**{T2.8}** · Layer 1 · Предусловие: исходники инфра-конструкторов.
Шаги: grep по `backend/app/infra/redis.py`, `db.py`, `llm.py`, `mcp.py`, `services/mcp_tool_resolver.py`, `mcp_server.py`, `api/routes/mcp_servers.py`, siem `infra/db.py` + `main.py` на числовые литералы таймаутов.
Ожидаемо: ни одного хардкод-литерала таймаута/retry — все значения берутся из `settings.*` (либо проброшены параметром). В частности: удалён `MCP_TIMEOUT = 30` из `mcp_tool_resolver.py`; нет литералов `30` в `mcp_server.py`/`mcp_servers.py`; нет `600`/`45`/`300` в `llm.py`.

**{T2.9}** · Layer 1 · Предусловие: `.env.example`.
Шаги: проверить присутствие переменных: `REDIS_SOCKET_TIMEOUT`, `REDIS_SOCKET_CONNECT_TIMEOUT`, `DB_STATEMENT_TIMEOUT_SECONDS`, `LLM_GUARD_TIMEOUT_SECONDS`, `LLM_SUMMARIZER_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `MCP_TIMEOUT_SECONDS` (секция Application); `SIEM_REDIS_SOCKET_TIMEOUT`, `SIEM_REDIS_SOCKET_CONNECT_TIMEOUT`, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS` (секция SIEM).
Ожидаемо: все 10 переменных задокументированы с комментарием про operational knobs; значения совпадают с дефолтами Settings.

**{T2.10}** · Layer 1 · Предусловие: `docker-compose.yml`.
Шаги: проверить блок `siem-service.environment`.
Ожидаемо: проброшены три переменные — `SIEM_REDIS_SOCKET_TIMEOUT: ${SIEM_REDIS_SOCKET_TIMEOUT:-5}`, `SIEM_REDIS_SOCKET_CONNECT_TIMEOUT: ${SIEM_REDIS_SOCKET_CONNECT_TIMEOUT:-5}`, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS: ${SIEM_DB_STATEMENT_TIMEOUT_SECONDS:-120}`. App-переменные приходят через `env_file: .env` (по прецеденту), отдельный проброс для `app` не требуется — подтвердить, что у сервиса `app` есть `env_file`.

**{T2.11}** · Layer 1 · Предусловие: siem Settings, дефолты `socket_timeout=5`, `xread_block_ms=1000`.
Шаги: вычислить инвариант OQ-D: `redis_socket_timeout` (сек) > `xread_block_ms`/1000.
Ожидаемо: 5 > 1 — инвариант держится. Блокирующий `XREADGROUP block=1000ms` помещается внутрь socket_timeout, спонтанного `TimeoutError` нет. Если реализован валидатор Settings (опционально по OQ-D) — проверить, что `SIEM_REDIS_SOCKET_TIMEOUT=0.5` при `xread_block_ms=1000` даёт `ValidationError` на старте. (Валидатор не обязателен; базовый кейс — проверка дефолтного соотношения.)

**{T2.12}** · Layer 1 · Предусловие: `backend/app/config.py`, property `langgraph_database_url`.
Шаги: инстанцировать Settings, прочитать `langgraph_database_url`.
Ожидаемо: URL без `+psycopg`-диалекта и содержит query-параметры `options=-c%20statement_timeout%3D120000` (URL-кодированные пробел и `=`) и `connect_timeout=5` (из 120s statement / 5s connect). Кандидат в автотест: проверить корректность URL-кодирования и значений. Дрейф-проверка: текущая реализация property (config.py:50-52) только убирает `+psycopg` — T2.4 должна её расширить.

**{T2.13}** · Layer 1 · Предусловие: исходник `backend/app/infra/llm.py` после T2.5.
Шаги: проверить `_build_chat_model` и фабрики.
Ожидаемо: `create_guard_llm` передаёт `timeout=settings.llm_guard_timeout_seconds` + `max_retries=settings.llm_max_retries`; `create_summarization_llm` — `timeout=settings.llm_summarizer_timeout_seconds` + `max_retries`; `create_llm_from_config` (чат) — только `max_retries`, без `timeout`. `LLMClassifierConfig.max_retries` (security/types.py, дефолт 3) НЕ затронут — это bounded-цикл на невалидный вывод, не openai-retry.

---

## Layer 2 — поведение

**{T2.14}** · Layer 2 · Предусловие: main app поднят; `REDIS_URL` указывает на недостижимый хост/порт (blackhole, напр. `redis://10.255.255.1:6379`).
Шаги: рестартовать main app с blackhole-URL; засечь время старта.
Ожидаемо: `create_redis` падает по `socket_connect_timeout` за ~5s (не висит), ловит исключение → возвращает `None` + warning `redis connection failed` (graceful, по дизайну main app); сервис стартует без Redis. Без фикса — connect висел бы бесконечно.

**{T2.15}** · Layer 2 · Предусловие: siem-service; `SIEM_REDIS_URL` на blackhole.
Шаги: рестартовать siem с blackhole-URL.
Ожидаемо: startup-ping упирается в `socket_connect_timeout` за ~5s и сервис падает fail-fast (siem не деградирует без Redis — это его core-зависимость), а не висит на старте.

**{T2.16}** · Layer 2 · Предусловие: main app + доступный Postgres.
Шаги: открыть сессию приложения; выполнить `SHOW statement_timeout`.
Ожидаемо: `120000` (ms) на app-engine (psycopg, через `connect_args options`). Аналогично для siem-engine (asyncpg, через `server_settings`) → `SHOW statement_timeout` = `120000`. Кандидат: проверить, что `create_engine` формирует драйвер-специфичный `connect_args`.

**{T2.17}** · Layer 2 · Предусловие: сессия приложения main app.
Шаги: выполнить через эту сессию `SELECT pg_sleep(130)`.
Ожидаемо: запрос отменяется на ~120s ошибкой statement timeout (`QueryCanceled`/`OperationalError`), не висит до 130s. (Маппинг ошибки в 504/503 — это T1; здесь проверяем только факт отмены.) Повторить для siem-engine. `👤` (требует ~2 мин ожидания и доступной БД — нагрузочно-ручной).

**{T2.18}** · Layer 2 · Предусловие: main app, доступны БД и LLM-ключ; reasoning-модель, способная думать >120s.
Шаги: запустить chat-turn, который суммарно идёт дольше 120s (длинная генерация / несколько ReAct-шагов).
Ожидаемо: **turn НЕ прерывается** statement_timeout'ом — подтверждает per-statement семантику (таймаут на отдельный SQL, не на транзакцию/turn). Это критичная страховка: `statement_timeout` рубит SQL, но НЕ открытую транзакцию вокруг LLM. `chat.py` рано коммитит request-сессию; `create_artifact` использует отдельный `session_factory`. `👤` (нужен LLM-ключ + долгая генерация).

**{T2.19}** · Layer 2 · Предусловие: исходники + запущенная БД.
Шаги: подтвердить, что `idle_in_transaction_session_timeout` НЕ установлен ни в одном engine/URL/миграции/конфиге; grep по репозиторию.
Ожидаемо: параметр отсутствует. Его наличие превратило бы statement-timeout в turn-killer (оборвало бы длинные turn по T2.18) — жёсткий запрет трека. На сессии: `SHOW idle_in_transaction_session_timeout` → `0` (отключён). Связка T2.18+T2.19 — главная регрессионная страховка трека.

**{T2.20}** · Layer 2 · Предусловие: main app, langgraph checkpointer/store инициализированы.
Шаги: на соединении langgraph-пула выполнить `SHOW statement_timeout`; прогнать chat-turn, пишущий checkpoint.
Ожидаемо: `120000` на langgraph-пуле (через libpq `options` в URL); `store.setup()`/`checkpointer.setup()` прошли; checkpoint пишется без ошибок connect (URL-кодирование `options` корректно парсится psycopg). `👤` частично (turn требует LLM-ключ; `SHOW`-проверка — без ключа).

**{T2.21}** · Layer 2 · Предусловие: main app; URL MCP-сервера, который принимает соединение, но не отвечает (или недостижимый порт за firewall, держащий коннект).
Шаги: `POST .../mcp-servers/test` с таким URL; засечь время.
Ожидаемо: ответ возвращается за ~`mcp_timeout_seconds` (дефолт 30s) c `TestConnectionResponse(success=False)`, не висит. При `MCP_TIMEOUT_SECONDS=7` — за ~7s. Подтверждает единый таймаут на всех MCP-путях (resolver/server/routes/infra). `👤` частично (нужен стенд с «молчащим» сервером; быстрее проверить автотестом проброса — T2.22).

**{T2.22}** · Layer 1/2 · Предусловие: исходники MCP-путей.
Шаги: сконструировать `build_mcp_connections(..., timeout=7)` и `MCPToolResolver(mcp_timeout=7)`; осмотреть результат.
Ожидаемо: `SSEConnection` получает `sse_read_timeout=7`, `StreamableHttpConnection` — `timeout=7`; `infra/mcp.py` больше НЕ создаёт connection без таймаута (закрытие F-RES-06); `fetch_remote_metadata`/`_test_connection` принимают и используют `timeout`. Кандидат в автотест (без сети — проверка connection-dict/kwargs).

**{T2.23}** · Layer 2 · Предусловие: оба сервиса со штатным доступным Redis.
Шаги: наблюдать логи siem-subscriber ~1–2 минуты при нормальной работе.
Ожидаемо: цикл `XREADGROUP` работает без спонтанных `TimeoutError` (socket_timeout 5s > block 1s); main app выполняет операции Redis (trace store) без регрессий по сравнению с до-фикса поведением.

**{T2.24}** · Layer 2 · Предусловие: main app + LLM-ключ, guard-классификатор активен; способ задержать ответ guard-LLM сверх 45s (мок/прокси с задержкой).
Шаги: вызвать chat с включённым guard, искусственно задержав ответ guard-LLM > 45s.
Ожидаемо: guard-вызов обрывается по `timeout=45s` → наблюдаемая деградация в CLEAN (D-ERR-6: `security_event` + `agent.guard.degraded`), а не зависание turn на 600s. `max_retries=2` означает до 2 повторов на транзиентном сбое. `👤` (нужен LLM-ключ + контролируемая задержка).

---

## Gate (минимальный набор для прохождения трека)

Обязательны перед пометкой фазы готовой:
- **{T2.1}** `make check` зелёный.
- **{T2.2}+{T2.3}** оба сервиса стартуют, `/health` зелёный.
- **{T2.6}+{T2.9}+{T2.10}** поля Settings + env во всех обязательных местах (`.env.example`, compose).
- **{T2.8}** нет хардкод-литералов таймаутов.
- **{T2.11}** инвариант `socket_timeout > xread_block`.
- **{T2.16}** `SHOW statement_timeout` = 120000 на обоих engine.
- **{T2.18}+{T2.19}** критичная страховка: длинный turn не рубится + нет `idle_in_transaction_session_timeout`.

## Список 👤 (требуют LLM-ключ / нагрузочную симуляцию / стенд)

- **{T2.17}** — `SELECT pg_sleep(130)`, ожидание ~2 мин на доступной БД.
- **{T2.18}** — длинный chat-turn >120s, нужен LLM-ключ.
- **{T2.20}** — частично: turn с checkpoint требует LLM-ключ (`SHOW` — без ключа).
- **{T2.21}** — частично: «молчащий» MCP-стенд (быстрее закрыть автотестом T2.22).
- **{T2.24}** — задержка guard-LLM >45s, нужен LLM-ключ + контролируемая задержка.
