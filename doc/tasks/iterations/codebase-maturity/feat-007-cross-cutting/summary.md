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
- [ ] T4 — siem error handling (полное зеркало)
- [ ] T2 — устойчивость + config
- [ ] T3 — agent error handling
- [ ] T5 — frontend обвязка

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
