# Summary: feat-007 — Cross-Cutting Error Handling

Журнал реализации итерации. Заполняется implementer'ами пофазно.

## Контекст
- Решения: `decisions.md` (D-ERR-1…11 + § Резолюции).
- План: `plan.md` + `plan-T1.md`…`plan-T5.md`.
- Тест-кейсы: `test-cases.md` + `test-cases-T1.md`…`test-cases-T5.md`.
- Конвенции: `doc/tech/conventions.md` § «Обработка ошибок».
- Порядок реализации (серийно, один worktree): **T1 → T4 → T2 → T3 → T5**.

## Прогресс
- [x] T1 — модель ошибок + барьерный стек (main app)
- [x] T4 — siem error handling (полное зеркало)
- [x] T2 — устойчивость + config
- [x] T3 — agent error handling
- [x] T5 — frontend обвязка

---

## Журнал фаз

### T1 — Модель ошибок + барьерный стек (main app)

**`make check` (ruff + mypy): зелёный.**

#### Что реализовано

**Фаза 1 — `backend/app/services/exceptions.py`**
Добавлена иерархия `AppError` (без импорта fastapi/HTTP):
- `AppError` — база с `code: str`, `status: int`, `detail: str`, `extensions: dict`.
- `NotFoundError` (404, `entity-not-found`).
- `ConflictError` (409, `conflict`).
- `SecurityPolicyViolationError` (422, `security-policy-violation`) — несёт `reason` в `extensions`.
- `UpstreamUnavailableError` (503 по умолчанию, `code`/`status` конфигурируются per-instance — для 502 vs 503).
- `EncryptionError` (500, `encryption-error`).
- `InvalidURLError` (400, `invalid-url`) — для DNS-сбоев в url_validator.
- `EntityNotFoundError` → подкласс `NotFoundError`: сохранён `__init__(entity, entity_id)`, id/имя в `args[0]`/`str(exc)` для логов, `detail="Resource not found"` (безопасно для клиента).
- `AuthError`-дерево оставлено как есть (F-API-08, OQ-4).

**Фаза 2 — `backend/app/api/problem.py` + `backend/app/main.py`**
Барьерный стек:
- `_app_error_handler` (Layer 1): `AppError` → `urn:learnflow:<code>` + `exc.status` + extensions.
- `_infra_exception_handler` (Layer 2): `DBAPIError` → 503 + `logger.error(exc_info=True)`.
- `_timeout_exception_handler` (Layer 2): `TimeoutError`/`asyncio.TimeoutError` → 504 + `logger.error(exc_info=True)`.
- `_validation_exception_handler` (F-API-14): сужен до `loc`/`msg`/`type`, убран `ctx`/`input`/`url`.
- `register_problem_handlers`: регистрирует все 5 handlers.
- Layer 3 (generic 500 + CORS, F-API-01): перехват `Exception` в `request_id_middleware` (ниже CORSMiddleware — ответ проходит обратно через CORS). `logger.error(exc_info=True)` с request-контекстом.
- `main.py`: удалён `entity_not_found_handler` и импорт `EntityNotFoundError` (покрыт Layer 1). Health endpoint → 503 problem+json при `OperationalError` (F-API-02).

**Фаза 3 — `sphere.py`, `user_memory.py`**
Убраны прямые `raise HTTPException(422, ...)` и импорт `fastapi`. Вместо них — `raise SecurityPolicyViolationError(reason=...)`. Лог `security_event=True` перед raise сохранён.

**Фаза 4 — `mcp_server.py`, `encryption.py`, `url_validator.py`**
- `url_validator.py`: DNS-сбой → `InvalidURLError(400)`, SSRF → `SecurityPolicyViolationError(422, reason="ssrf_private_ip")`. Убран сырой `ValueError`.
- `encryption.py`: `decrypt` оборачивает `cryptography.fernet.InvalidToken` в `EncryptionError` с `logger.error(exc_info=True)` (F-SVC-11, 🟢-находка включена).
- `mcp_server.py`: убран `from fastapi import HTTPException`. `_fetch_or_503` — `validate_url` теперь кидает domain exceptions напрямую; `fetch_remote_metadata` failure → `UpstreamUnavailableError(code="mcp-unreachable", status=503) from exc`, `logger.warning(exc_info=True)` (без `str(exc)` в теле). `_guard_blob` → `SecurityPolicyViolationError`. `_apply_update_fields` / `_validate_and_encrypt`: encryption unavailable → `UpstreamUnavailableError(code="encryption-not-configured", status=503)` (OQ-2 resolution: 503).

**Фаза 5 — `auth.py`**
`register` оборачивает `self._user_repo.create(user)` в `try/except IntegrityError as e: raise UsernameAlreadyExistsError from e`. Быстрый pre-check `get_by_name` сохранён. Локальный handler `routes/auth.py` маппит `UsernameAlreadyExistsError` → 409 (без изменений).

**Фаза 6 — `export.py`, `artifacts.py`**
`convert_md_to_pdf` оборачивает `pdfkit.from_string` в `try/except Exception` → `UpstreamUnavailableError(code="pdf-render-failed", status=502) from e` (F-API-03). Таймаут параметризован в `_PDF_TIMEOUT_SECONDS = 30` с TODO-ссылкой на T2 (D-ERR-11: Settings-поле заведёт T2). `artifacts.py` не изменялся — исключение пробрасывается через `anyio.to_thread.run_sync` на барьер.

**Фаза 7 — `routes/messages.py`**
`_event_generator` обёрнут в `try/except Exception` → терминальное `data: {"type":"error",...}\n\n` + `logger.error(exc_info=True)`. Покрывает setup-фазу (до try-блока runner) и сериализацию (F-API-05).

**Фаза 8 — `routes/feedback.py`**
- `_get_langfuse_client`: `except Exception` → `UpstreamUnavailableError(code="langfuse-unavailable", status=503)` с `exc_info=True` (было: без `exc_info`).
- `set_feedback`, `delete_feedback`: `except Exception` сужен до `(httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError)` → `UpstreamUnavailableError`. Прочие исключения (TypeError/AttributeError/программные баги) пробрасываются на generic barrier → 500 (F-API-04).

#### Отклонения от плана / решения

- **OQ-1 (validate_url статус)**: DNS→400 (`InvalidURLError`), SSRF→422 (`SecurityPolicyViolationError(reason="ssrf_private_ip")`) — по резолюции оркестратора из task-prompt.
- **OQ-2 (MCP_ENCRYPTION_KEY не сконфигурирован)**: 503 (`UpstreamUnavailableError(code="encryption-not-configured", status=503)`) — по резолюции оркестратора.
- **OQ-3 (generic-500 + CORS)**: middleware-перехват в `request_id_middleware` (ниже CORS) — по умолчанию из плана, не потребовал архитектурного решения.
- **OQ-5 (feedback.py)**: включён в T1 — по резолюции оркестратора.
- **OQ-6 (таймаут PDF)**: `_PDF_TIMEOUT_SECONDS = 30` как параметр функции, Settings-поле — в T2 (TODO в коде).
- **OQ-7 (🟢 EncryptionError)**: включён — по резолюции оркестратора.
- **`InvalidURLError`**: не была в явном списке иерархии (план говорил «OQ-1 → архитектору»), но резолюция оркестратора DNS→400 требовала нового типа. Добавлен как `AppError` (400, `invalid-url`) — минимальный и органичный в иерархии.

---

### T4 — SIEM error handling (полное зеркало)

**`make check` (ruff + mypy): зелёный.**

#### Что реализовано

**Фаза 1 — `siem_service/exceptions.py` + `siem_service/api/problem.py` + `siem_service/main.py`**

Создана собственная иерархия `AppError` в siem (зеркало backend, OQ-C):
- `AppError` — база с `code: str`, `status: int`, `detail: str`, `extensions: dict`.
- `NotFoundError` (404, `entity-not-found`).
- `ConflictError` (409, `conflict`).

Барьерный стек в `siem_service/api/problem.py` расширен до 3 слоёв (зеркало T1):
- `_app_error_handler` (Layer 1): `AppError` → `urn:learnflow:<code>` + `exc.status`.
- `_infra_exception_handler` (Layer 2): `DBAPIError` → 503 + `logger.error(exc_info=True)`.
- `_timeout_exception_handler` (Layer 2): `TimeoutError`/`asyncio.TimeoutError` → 504 + `logger.error(exc_info=True)`.
- `_validation_exception_handler`: сужен до `loc`/`msg`/`type` (убран `ctx`/`input`/`url`), зеркало T1 (F-API-14).
- Layer 3 (generic 500 + CORS): middleware `_generic_exception_middleware` в `main.py` ниже `CORSMiddleware` — тот же механизм, что T1 (`request_id_middleware`). OQ-2 закрыт через middleware-подход, CORS-on-500 работает корректно.

**Фаза 2 — `siem_service/pipeline/subscriber.py` + `siem_service/config.py`**

Разделение барьеров в `_process_single_message` (D-ERR-7):
- `ValidationError` (poison): drop + XACK + метрика `siem_events_invalid`. Поведение сохранено, event_id исправлен.
- `OperationalError`/`DBAPIError` (транзиент): **НЕ XACK** (остаётся в PEL) + метрика `siem_events_transient` + `logger.warning(exc_info=True)`.
- Bounded delivery-count (OQ-E): `_get_delivery_count` через `xpending_range` перед обработкой. После `> max_delivery_attempts` → terminal drop + XACK + `logger.error` с payload + метрика `siem_events_failed_terminal`.
- `event_id_str` извлекается из распарсенного `event_dict` (фолбэк — `message_id`), не из raw `payload_dict` (F-SIEM-04).
- `_read_pending` добавлено `error=str(e)` в `logger.warning` (F-SIEM-08).
- `SIEM_MAX_DELIVERY_ATTEMPTS` добавлен в `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml` (D-ERR-11).

**Фаза 3 — `siem_service/pipeline/meta_emitter.py`**

- `exc_info=True` в `logger.error` при сбое эмиссии (F-SIEM-03).
- `_metrics: defaultdict(int)` с ключом `meta_events_dropped` — счётчик дропнутых meta-событий.
- Исправлен stale-комментарий строки 45: XADD отправляет `{"data": ...}`, event_id внутри JSON-payload, не как отдельное поле stream-записи.

**Фаза 4 — `siem_service/domain/schemas.py` + `siem_service/correlation/strategies.py`**

- `RuleCreateRequest.rule_type` → `Literal["threshold", "sequence", "aggregate"]` (F-SIEM-05).
- `RuleCreateRequest.severity` → `Literal["info", "warning", "critical"]`.
- `RuleUpdateRequest` — те же поля `Literal | None`.
- `get_strategy`: `logger.warning` + `raise ValueError` для неизвестного типа; per-rule `try/except` в `CorrelationEngine` перехватывает, engine продолжает (F-SIEM-G4).

**Фаза 5 — `siem_service/api/routes.py` + `siem_service/services.py`**

- Убрана мёртвая ветка `if rule is None: raise HTTPException(500)` из `create_rule` (F-SIEM-06).
- `RuleService.create_rule` ловит `IntegrityError` → `ConflictError` (409); возврат сужен до non-Optional `RuleResponse`.
- Все `if not X: raise HTTPException(404)` в роутах заменены на `raise NotFoundError(...)` (OQ-C: полное зеркало, роуты на доменные исключения): `get_alert`, `patch_alert`, `get_rule`, `update_rule`, `delete_rule`.
- `HTTPException` сохранён для 401 (`_require_user_id`) и 400 (update пустой PATCH).

#### Отклонения от плана / решения

- **OQ-C (иерархия AppError в siem)**: реализовано как «полное зеркало» — собственные `exceptions.py`, барьер 3 слоя, роуты на доменные исключения. Scope T4 расширен относительно изначального плана (где упоминался вариант «только слои 2+3»).
- **OQ-2 (CORS-on-500 в siem)**: решено через `@app.middleware("http")` `_generic_exception_middleware` в `main.py` (ниже CORS) — зеркало механизма `request_id_middleware` в T1, без `request_id`-биндинга (siem его не имеет).
- **OQ-4 (Literal severity)**: локальный `Literal` в `schemas.py` (не переиспользование типа из `siem_contracts`) — достаточно для валидации; `get_strategy` для неизвестного типа → `raise ValueError` (поднимается в per-rule catch CorrelationEngine).
- **OQ-5 (где ловить IntegrityError)**: поймано в `RuleService.create_rule` (сервисный слой) → `ConflictError`. Pre-check через `get_rule_by_name` не добавлен: IntegrityError как единственная защита от TOCTOU; pre-check остаётся кандидатом в follow-up.

---

### T2 — Устойчивость + конфигурирование (таймауты/retry через Settings/env)

**`make check` (ruff + mypy): зелёный.**

#### Что реализовано

**Фаза T2.1 — Декларация knob'ов (Settings + .env.example + docker-compose.yml)**

- `backend/app/config.py`: добавлены поля `redis_socket_timeout: float = 5.0`, `redis_socket_connect_timeout: float = 5.0`, `db_statement_timeout_seconds: int = 120`, `llm_guard_timeout_seconds: float = 45`, `llm_summarizer_timeout_seconds: float = 300`, `llm_max_retries: int = 2`, `mcp_timeout_seconds: int = 30`, `pdf_conversion_timeout_seconds: int = 30`.
- `services/siem-service/siem_service/config.py`: добавлены `redis_socket_timeout: float = 5.0`, `redis_socket_connect_timeout: float = 5.0`, `db_statement_timeout_seconds: int = 120` (с комментарием OQ-D инварианта: `socket_timeout > xread_block_ms/1000`).
- `.env.example`: добавлены 8 app-переменных (секция «Operational knobs») и 3 SIEM-переменных с документацией инварианта OQ-D.
- `docker-compose.yml` (siem-service.environment): добавлены `SIEM_REDIS_SOCKET_TIMEOUT`, `SIEM_REDIS_SOCKET_CONNECT_TIMEOUT`, `SIEM_DB_STATEMENT_TIMEOUT_SECONDS`.
- `.env.local.example` — не трогали (по плану T2.1: дефолты подходят для local dev).

**Фаза T2.2 — Redis socket-таймауты (оба сервиса)**

- `backend/app/infra/redis.py`: `aioredis.from_url(...)` расширен `socket_timeout=settings.redis_socket_timeout`, `socket_connect_timeout=settings.redis_socket_connect_timeout`. Startup-ping автоматически попадает под connect-таймаут — graceful degradation на blackhole-URL за ~5s.
- `services/siem-service/siem_service/main.py`: аналогично для lifespan-клиента. OQ-D инвариант держится: `socket_timeout=5s > xread_block=1s`.

**Фаза T2.3 — Postgres `statement_timeout` (оба engine)**

- `backend/app/infra/db.py` (psycopg3): `create_async_engine` расширен `connect_args={"options": f"-c statement_timeout={ms}"}`.
- `services/siem-service/siem_service/infra/db.py` (asyncpg): `connect_args={"server_settings": {"statement_timeout": str(ms)}}`.
- `idle_in_transaction_session_timeout` намеренно НЕ добавлен — только per-statement SQL, длинные agent-turn'ы не рубятся (T2.18/T2.19).

**Фаза T2.4 — LangGraph checkpointer/store таймауты**

- `backend/app/config.py`, property `langgraph_database_url`: URL расширен libpq query-параметрами через `urllib.parse.urlencode(quote_via=quote)`. Результат: `postgresql://...@host/db?options=-c%20statement_timeout%3D120000&connect_timeout=5`. Единственный рычаг для обоих (saver/store не принимают connection-kwargs). `connect_timeout` переиспользует значение `redis_socket_connect_timeout` (5s).

**Фаза T2.5 — LLM таймауты и `max_retries`**

- `backend/app/infra/llm.py`, `_build_chat_model`: добавлены `timeout: float | None = None`, `max_retries: int | None = None`. `ChatOpenAI` принимает `timeout` через alias `request_timeout` (проверено по installed package).
- `create_guard_llm`: `timeout=settings.llm_guard_timeout_seconds` (45s) + `max_retries=settings.llm_max_retries` (2).
- `create_summarization_llm`: `timeout=settings.llm_summarizer_timeout_seconds` (300s) + `max_retries`.
- `create_llm_from_config` (основной чат): только `max_retries` — timeout намеренно не вводим (D-ERR-9: reasoning-модели, openai-дефолт 600s).
- `LLMClassifierConfig.max_retries` (bounded-цикл на невалидный вывод) — не тронут; бизнес-инвариант агента.

**Фаза T2.6 — MCP единый таймаут**

- `backend/app/infra/mcp.py`: `_build_connection`, `build_mcp_connections`, `create_mcp_client` расширены обязательным `timeout: int`; прокинут в `SSEConnection(sse_read_timeout=float(timeout))` и `StreamableHttpConnection(timeout=timeout)`.
- `backend/app/services/mcp_tool_resolver.py`: удалена константа `MCP_TIMEOUT = 30`; `MCPToolResolver.__init__` получил `mcp_timeout: int = 30`; `_fetch_tools` использует `self._mcp_timeout`.
- `backend/app/services/mcp_server.py`: `_build_test_connection` и `fetch_remote_metadata` расширены параметром `timeout: int`; `McpServerService` хранит `self._mcp_timeout`, передаёт в `_fetch_or_503`.
- `backend/app/api/routes/mcp_servers.py`: `_test_connection(url, transport, api_key, timeout)`; `_build_mcp_service` берёт `mcp_timeout` из `request.app.state.settings`; три `test_*_server` хендлера передают `settings.mcp_timeout_seconds`.
- `backend/app/main.py`: `_validate_builtin_mcp` принимает `timeout: int`; вызовы `fetch_remote_metadata`, `create_mcp_client`, `MCPToolResolver` обновлены с `settings.mcp_timeout_seconds`.

**`_PDF_TIMEOUT_SECONDS` → Settings**

- `backend/app/api/export.py`: удалена константа `_PDF_TIMEOUT_SECONDS = 30` и TODO-комментарий T2. Функция сохраняет `timeout: int = 30` как fallback-дефолт.
- `backend/app/api/routes/artifacts.py`: `download_artifact` получил `request: Request`; timeout берётся из `settings.pdf_conversion_timeout_seconds` и передаётся через `functools.partial(convert_md_to_pdf, timeout=...)`.

---

### T3 — Agent error handling

**`make check` (ruff + mypy): зелёный. Точечные автотесты: 10/10 pass.**

#### Что реализовано

**Фаза 1 — `packages/siem-contracts/siem_contracts/vocabulary.py` + `__init__.py`**
- Константа `AGENT_GUARD_DEGRADED = "agent.guard.degraded"` добавлена в блок `# Agent security guard events - cross-checkpoint degradation`.
- Строка `"agent.guard.degraded"` добавлена в `EventType` Literal (mypy-проверяемо на call-site в guard.py).
- `__init__.py`: импорт и экспорт `AGENT_GUARD_DEGRADED` в `__all__`. Добавление аддитивно — существующие константы не тронуты.

**Фаза 2 — `backend/app/agent/security/types.py`**
- В `ClassifierResult` добавлено поле `degraded: bool = False`. Позволяет guard.py различать «честный CLEAN» и «CLEAN из деградации» (корень F-AGT-04).

**Фаза 2 — `backend/app/agent/security/classifier.py`**
- Ветка исчерпания ретраев (конец цикла) возвращает `ClassifierResult(..., degraded=True)`. Существующий `logger.warning("classifier retries exhausted...")` сохранён (внутренний WARNING ретраев).

**Фаза 3 — `backend/app/agent/security/guard.py`**
- Импорт `AGENT_GUARD_DEGRADED` из `siem_contracts`.
- **Дорога 1** (`except Exception`, LLM-исключение): заменён `event_type=AGENT_GUARD_INPUT_CLASSIFIER_INJECTION` на `AGENT_GUARD_DEGRADED`; уровень поднят с `warning` → `error`; в `metadata` добавлен `"direction": direction.value`. Снято два дефекта F-AGT-03: (а) INPUT-событие на OUTPUT-checkpoint'ах, (б) семантический конфликт `event_type=…INJECTION` при `verdict="clean"`.
- **Дорога 2** (после успешного `classify`, если `classifier_result.degraded`): новая ветка перед injection-блоком — возвращает `GuardResult(detection_layer=GRACEFUL_DEGRADATION, verdict=CLEAN, details={"reason": "retries_exhausted"})` + `logger.warning(security_event=True, event_type=AGENT_GUARD_DEGRADED, severity="critical", metadata={checkpoint, direction, detection_layer, verdict})`. Закрыт F-AGT-04 — дорога больше не тихая.
- Блок injection-события не срабатывает при degraded (verdict=CLEAN) — порядок ветвления сохранён.

**Фаза 4 — `backend/app/agent/graph.py`**
- Модульная функция-обработчик `_handle_tool_error(exc: Exception) -> str`: логирует `logger.error("tool execution failed", error_type=type(exc).__name__, exc_info=exc)`, возвращает константу `_TOOL_ERROR_MESSAGE` — нейтральное сообщение без внутренностей стека/DSN.
- `ToolNode(tools)` → `ToolNode(tools, handle_tool_errors=_handle_tool_error)`. Любое исключение в tool → `ToolMessage(status="error")`, ReAct-шаг закрывается, thread остаётся валидным. Callable вызывается как `flag(exc)` (проверено по установленному langgraph-prebuilt 1.0.8).

**Фаза 5 — `backend/app/agent/runner.py`**
- Барьер `except Exception` стрима: `logger.warning("agent stream error", error=str(e))` → `logger.error("agent stream error", error_type=type(e).__name__, exc_info=e)`. Оператор теперь видит тип и стек. Трансляция клиенту (`normalize_error_message`) не тронута (F-AGT-06).

**Фаза 6 — `doc/tech/security-events.md`**
- Добавлена секция «Security Guard Events - Degradation (cross-checkpoint)» с записью `agent.guard.degraded | critical | LLM guard degraded to CLEAN (LLM exception or classifier retries exhausted) | request_id, thread_id, user_id`.

**Точечные автотесты** (`doc/tasks/.../tests/`):
- `test_tool_node_handle_errors.py`: T3.3 (thread валиден + re-entry), T3.4 (logged error+exc_info, нет утечки контента), T3.10 (core-store fail-fast сохранён).
- `test_guard_degradation.py`: T3.2 (import smoke), T3.5 (road 1 INBOUND), T3.6 (road 1 OUTBOUND, direction=outbound), T3.7 (road 2 retries_exhausted), T3.8a/b (ClassifierResult.degraded signal), T3.9 (injection-путь не затронут).
- Итого: **10 тестов, 10 pass**.

#### Отклонения от плана / решения

- **Уровень лога дороги 1**: план (`plan-T3.md`) указывал `logger.warning` для road 1, но тот же план (§ Фаза 5) и decisions.md (OQ-B) требуют `logger.error` для security_event деградации. Применён `error` — последовательно с runner.py и смысловой тяжестью события.
- **conftest.py**: добавлен в папку тестов для разрешения `app.*` импортов (тесты лежат вне `backend/tests/`).

---

#### Отклонения от плана / решения

- **OQ-2 (connect_timeout для langgraph)**: переиспользован `redis_socket_connect_timeout` (дефолт 5s) вместо отдельного поля — план допускал оба варианта; значения эквивалентны в типичных сценариях.
- **Дефолты `mcp_timeout` в сигнатурах**: `fetch_remote_metadata`, `MCPToolResolver.__init__`, `McpServerService.__init__` имеют дефолт `= 30` как fallback — все основные callsites явно передают из Settings.
- **`StreamableHttpConnection.timeout`**: тип аннотации `timedelta`; передаём `int` с `# type: ignore[typeddict-item]` — унаследовано из T1, runtime принимает корректно.

---

### T5 — Frontend error handling (обвязка)

**`make check-fe` (tsc + ESLint + Prettier --check): зелёный.**

#### Что реализовано

**Фаза 1 — `frontend/src/shared/lib/api-error.ts` (новый файл)**

Единый парсер RFC 9457 problem+json. Два экспорта:
- `getProblemMessageFromBody(status, body)` — извлекает сообщение из тела: `detail` → `title` → категория по статусу. Используется и внутри `getApiErrorMessage`, и напрямую в fetch-ветке SSE.
- `getApiErrorMessage(error: unknown): string` — единая точка входа: `AxiosError` с `response` → `getProblemMessageFromBody`; `AxiosError` без `response` (`ECONNABORTED` → «Превышено время ожидания», прочее → «Сервер недоступен»); не-`AxiosError` → «Произошла ошибка, попробуйте позже».
- Типобезопасный type guard `isProblemBody` без поля `any` — по образцу `security-error.ts`.
- `security-error.ts` не изменялся: разделение концернов сохранено.

**Фаза 2 — axios `timeout` (D-ERR-9, D-ERR-11, F-FE-01)**

- `frontend/src/shared/api/client.ts`: `apiClient` — `timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30000`.
- `frontend/src/shared/api/security.ts`: `siemClient` — тот же timeout из той же env-переменной (дрейф-фикс F-FE-01: close twin).
- Env-переменная `VITE_API_TIMEOUT_MS` задокументирована в корневом `.env.example` (OQ-F).

**Фаза 3 — Дефолты `QueryClient` (F-FE-02)**

- `frontend/src/app/providers/QueryProvider.tsx`: `QueryClient` с `defaultOptions` + `QueryCache` + `MutationCache`.
- Предикат `shouldRetryQuery`: 4xx → `false` (не ретраить); 5xx/сеть → `failureCount < 2` (bounded, согласовано с backend `max_retries=2`).
- `defaultOptions.mutations.retry: false` — побочные эффекты не ретраим.
- `QueryCache.onError` и `MutationCache.onError`: централизованный `logger.error` с `getApiErrorMessage(error)`. Подача пользователю (тост) — backlog (D-ERR-8 подтверждает: здесь только лог).

**Фаза 4 — Применение парсера (F-FE-03/04/05/06/07/09)**

- `SecurityRules.tsx`: error-блок `useRules` + toggle-catch → `getApiErrorMessage`.
- `SecurityAlerts.tsx`: error-блок `useAlerts` → `getApiErrorMessage`.
- `SecurityEvents.tsx`: error-блок `useEvents` → `getApiErrorMessage`.
- `RuleForm.tsx`: submit-catch → `getApiErrorMessage` вместо `err.message`.
- `AuthGate.tsx`: семиуровневая `in`-проверка заменена одной строкой `setError(getApiErrorMessage(err))`.
- `CreateProjectModal.tsx`: добавлен `try/catch` вокруг `mutateAsync`; инлайн `<p className="text-sm text-destructive">` в разметке модалки.
- `ProjectActions.tsx`: `onError` в rename-мутации → `setRenameError`; `onError` в delete-мутации → `setDeleteError`; инлайн-сообщения в соответствующих диалогах.
- `MCPServerForm.tsx`: `isSecurityViolation(error) ? SECURITY_VIOLATION_MESSAGE : error ? getApiErrorMessage(error) : null` — security-ветка сохранена.
- `MCPServersSection.tsx`: `handleTest.onError` → `getApiErrorMessage(err)` (заменён «Connection failed»).
- `useAgentStream.ts`: `!response.ok` → `getProblemMessageFromBody(status, body)` через `response.json()` в try/catch вместо `` `HTTP ${response.status}` ``.

**Фаза 5 — SSE: first-byte timeout + защита JSON.parse (D-ERR-9, F-FE-10)**

- `useAgentStream.ts`: константа `FIRST_BYTE_TIMEOUT_MS` из `VITE_SSE_FIRST_BYTE_TIMEOUT_MS` (fallback → `VITE_API_TIMEOUT_MS` → 30 000 мс). Флаг `timedOut`; `firstByteTimer` запускается до первого `fetch`, снимается после `response.ok`. При срабатывании: `controller.abort()` + `endStream()` + `onError("Превышено время ожидания")`. В catch: `AbortError && timedOut` → тихий return (timeout уже обработан).
- `JSON.parse(line.slice(6))` обёрнут в `try/catch`: `logger.warn("[SSE] Malformed frame, skipping")` + `continue` — стрим не падает, уже полученный текст сохраняется.
- Env-переменная `VITE_SSE_FIRST_BYTE_TIMEOUT_MS` задокументирована в корневом `.env.example`.

**Фаза 6 — FeedbackButtons: откат оптимистичного лайка (F-FE-08)**

- `frontend/src/pages/chat/ui/FeedbackButtons.tsx`: `prevFeedback = feedback` до обновления; `request.catch(err => { logger.warn(...); setFeedback(prevFeedback); })` — откат при ошибке.

**Фаза 7 — Нормализация языка сообщений (F-FE-11)**

- `AuthGate.tsx`: «Password must be at least 8 characters» → «Пароль должен содержать не менее 8 символов»; «Passwords do not match» → «Пароли не совпадают».
- `useAgentStream.ts`: «Connection lost» → «Соединение прервано»; «Connection error» → «Ошибка соединения».
- `ErrorBoundary.tsx`: «Something went wrong» → «Что-то пошло не так»; «An unexpected error occurred.» → «Произошла непредвиденная ошибка.»; «Reload page» → «Обновить страницу».
- `ChatView.tsx`: «Failed to load chat.» → «Не удалось загрузить чат.»
- `ProjectList.tsx`: «Failed to load projects» → «Не удалось загрузить проекты»

**Фаза 8 — Сверка конвенций (дрейф-фикс)**

- `doc/tech/conventions.md` § Optimistic vs пессимистичные: исправлена строка «Единственный оптимистичный патч — `security_block`…» — теперь упоминаются оба оптимистичных патча (`security_block` + `FeedbackButtons` с откатом).

#### Открытые вопросы — резолюции

- **OQ-2 (`VITE_SSE_FIRST_BYTE_TIMEOUT_MS` vs переиспользование)**: заведена отдельная `VITE_SSE_FIRST_BYTE_TIMEOUT_MS` (семантически чище; fallback на `VITE_API_TIMEOUT_MS` если не задана). Обе задокументированы в корневом `.env.example` (OQ-F).
- **OQ-3 (глобальный `onError` без UI)**: подтверждено — `QueryCache/MutationCache.onError` = только `logger.error`, без тоста. Полноценная подача ждёт тост-итерации (backlog).
- **OQ-4 (F-FE-08 откат)**: включён в трек как точечный correctness-фикс (фаза 6).
