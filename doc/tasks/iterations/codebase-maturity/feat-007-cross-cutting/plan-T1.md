# plan-T1 — Модель ошибок + барьерный стек (main app)

Фрагмент плана трека T1 итерации feat-007. Нормы — `conventions.md` § Обработка ошибок (+ § REST API, § DB-сессии, § FastAPI, § Logging). Решения — `decisions.md` D-ERR-1…D-ERR-3, D-ERR-10/11. Findings — `audit-raw-01-api-boundary.md`, `audit-raw-02-services-db.md`. Тест-кейсы как самостоятельные документы пишутся отдельной фазой позже; здесь у каждой фазы — подход к verification.

Скоуп — только main app (`backend/`). Зеркало барьера в `siem_service/` — трек T4, не трогаем.

---

## Фаза 1 — Иерархия `AppError` в `exceptions.py`

**Цель.** Завести доменную базу `AppError` (машинный `code` + дефолтный `status` + безопасный для клиента `detail`; без импорта fastapi / знания про транспорт) и подклассы под карту D-ERR-3. Существующий `EntityNotFoundError` встроить в иерархию, **не ломая** его конструктор `(entity, entity_id)` и имя (импортируется из 6 мест — `project.py`, `artifact.py`, `chat.py`, `services/__init__.py`, `main.py`). `str(exc)`/`args` сохраняют id для лога; `detail` отдаёт клиенту обобщённое сообщение без id/имени класса (F-API-06).

**Изменения по файлам.**
- `backend/app/services/exceptions.py`:
  - `class AppError(Exception)` с атрибутами `code: str`, `status: int`, `detail: str` (+ опциональные `extensions: dict` для `reason`/`errors`).
  - Подклассы: `NotFoundError`(404, `entity-not-found`), `ConflictError`(409, `conflict`), `SecurityPolicyViolationError`(422, `security-policy-violation`, несёт `reason`), `UpstreamUnavailableError`(503, конфигурируемый `code`/`status` — для 502 vs 503), `EncryptionError`(500/503 — см. OQ-7). Валидацию входа (422) на доменном уровне — см. OQ-1 (нужна ли `InvalidInputError`).
  - `EntityNotFoundError` → подкласс `NotFoundError`: сохраняет `__init__(entity, entity_id)`, кладёт id в `args`/лог, `detail="Resource not found"`.
  - `AuthError`-дерево (Invalid/Expired/Replay/UsernameAlreadyExists) — **пока оставить как есть**, обрабатывается локально в `routes/auth.py` (эталон F-API-08). Консолидация в `AppError` — OQ-4.

**Verification.** `make check` (ruff + mypy): импорты не сломаны, `__init__.py` экспорт цел. Поведения ещё нет (барьер не подключён) — это чистый рефактор типов. Кандидат в автотест: конструирование каждого подкласса → корректные `code`/`status`/`detail`; `EntityNotFoundError("Project", id)` не протекает id в `detail`.

---

## Фаза 2 — Барьерный стек в `problem.py` + регистрация в `main.py`

**Цель.** Три слоя перехвата на границе приложения (D-ERR-2): (1) `AppError`→problem+json по `exc.status` с `type_=urn:learnflow:<code>` + extensions; (2) инфра-исключения (`DBAPIError`/`OperationalError`→503, timeout→504) + лог `exc_info`; (3) generic `Exception`→500 problem+json без внутренностей + лог `exc_info`. Снять ad-hoc `@app.exception_handler(EntityNotFoundError)` из `main.py` (теперь покрыт слоем 1). Health честно отдаёт 503 при недоступной БД (F-API-02). Попутно F-API-14: валидационный handler отдаёт выбранный набор полей (`loc`/`msg`/`type`), не сырой `exc.errors()`.

**Ключевой нюанс — CORS на 500 (F-API-01).** `ServerErrorMiddleware` (Starlette, обрабатывает catch-all `Exception` через `add_exception_handler(Exception)`) сидит **выше** `CORSMiddleware` → 500-ответ не получает CORS-заголовки, браузер видит CORS-ошибку вместо тела 500. Слои 1 и 2 (`AppError`, инфра) проходят через внутренний `ExceptionMiddleware` (ниже CORS) — CORS к ним применяется штатно. Проблема только у last-resort 500. План: ловить generic `Exception` в `request_id_middleware` (оборачивает `call_next` в try/except, оно ниже CORS → ответ проходит обратно через CORS) → `problem_response(500, …)` + `logger.error(exc_info=True)` с request-контекстом. Это закрывает сразу два под-пункта F-API-01 (CORS на 500 и отсутствие лога в `request_id_middleware`). Альтернатива — `add_exception_handler(Exception)` + перестановка CORS в самый внешний слой; выбор механизма — OQ-3.

**Изменения по файлам.**
- `backend/app/api/problem.py`: `_app_error_handler`; `_infra_exception_handler` (на `DBAPIError`; timeout — `TimeoutError`/`asyncio.TimeoutError`→504); сузить выдачу `_validation_exception_handler` (F-API-14); расширить `register_problem_handlers`.
- `backend/app/main.py`: убрать `entity_not_found_handler` и импорт `EntityNotFoundError` (если больше не нужен); зарегистрировать новые handlers; добавить try/except + лог в `request_id_middleware` (generic 500); `/health` → 503 problem+json при `OperationalError` на `SELECT 1`.

**Verification.** `make check`. Ручные/curl: (a) `make docker-up-db` затем остановить БД → `GET /health` отдаёт 503 `application/problem+json`; (b) маршрут, бросающий необработанное исключение, → 500 problem+json **с** заголовком `Access-Control-Allow-Origin` при запросе с `Origin` (проверить наличие CORS на 500); (c) `EntityNotFoundError`-путь (несуществующий project) → 404 problem+json `type=urn:learnflow:entity-not-found`, без утечки id; (d) невалидный body → 422 с урезанным `errors`. Кандидаты в автотесты: на тестовом app по handler на каждый слой (AppError→status, DBAPIError→503, TimeoutError→504, generic→500 + отсутствие внутренностей в теле).

---

## Фаза 3 — Путь B→A: `sphere.py` + `user_memory.py`

**Цель.** Убрать прямые `raise HTTPException(422, …)` из доменных сервисов (F-SVC-02) → `raise SecurityPolicyViolationError(reason=…)`; маппинг в 422 ушёл на барьер (Фаза 2). Лог `security_event=True` перед raise — сохранить как есть. Снять импорт `fastapi`.

**Изменения по файлам.**
- `backend/app/services/sphere.py`: `LangGraphSphereService.update` (строки ~131) — `HTTPException(422, security_policy_violation)` → `SecurityPolicyViolationError`.
- `backend/app/services/user_memory.py`: `update_instructions` (строки ~71) — то же.

**Verification.** `make check` (импорт fastapi ушёл — ruff `F401`). Curl: `PUT` KS-сферы и custom instructions с injection-payload → 422 problem+json `type=urn:learnflow:security-policy-violation` + extension `reason`; security-событие пишется в лог. Кандидат в автотест: сервис на injection-вердикте бросает `SecurityPolicyViolationError` с правильным `reason`.

---

## Фаза 4 — Путь B→A: `mcp_server.py` (+ `encryption.py`, `url_validator.py`)

**Цель.** Перевести все `HTTPException` в `mcp_server.py` на доменные исключения и починить гигиену `_fetch_or_503` (F-SVC-02, F-SVC-03):
- injection metadata (строки ~317) → `SecurityPolicyViolationError(reason=…)` (422).
- `mcp_unreachable` (строки ~271) → `UpstreamUnavailableError(code="mcp-unreachable", status=503)`; `from exc` вместо `from None` (сохранить цепочку), `logger.warning(..., exc_info=True)`, **не** отдавать `str(exc)` клиенту (стабильный код вместо сырого reason).
- `validate_url` ValueError (строки ~265/352/387) → доменное исключение; статус — OQ-1.
- `MCP_ENCRYPTION_KEY not configured` (строки ~371/399) → доменное исключение; статус — OQ-2.
- F-SVC-11: `EncryptionService.decrypt` (`encryption.py`) — сырой `cryptography.fernet.InvalidToken` → `EncryptionError` с логом (опортунистически, 🟢; подтвердить — OQ-7).

**Изменения по файлам.**
- `backend/app/services/mcp_server.py` (основное), `backend/app/services/encryption.py` (EncryptionError), `backend/app/services/url_validator.py` (опц. — развести DNS vs SSRF, F-SVC-10, OQ-1).

**Verification.** `make check` (fastapi-импорт ушёл). Curl: создать MCP-сервер с недоступным URL → 503 problem+json `type=urn:learnflow:mcp-unreachable` без сырого `str(exc)` в теле, но `exc_info` в логе; injection в метаданных → 422; невалидный URL → статус по OQ-1. Кандидаты в автотесты: `_fetch_or_503` на сетевой ошибке бросает `UpstreamUnavailableError` с сохранённой `__cause__`.

---

## Фаза 5 — `auth.register`: IntegrityError(unique) → 409 (F-SVC-01)

**Цель.** TOCTOU-гонка при регистрации: после быстрой happy-path проверки `get_by_name`, второй параллельный запрос ловит unique-violation на flush → сейчас сырой `IntegrityError` → 500. Ловить `IntegrityError` (unique на `User.name`) → `raise UsernameAlreadyExistsError`. Локальный handler в `routes/auth.py:145` уже мапит `UsernameAlreadyExistsError`→409 — барьер/роут менять не нужно.

**Изменения по файлам.**
- `backend/app/services/auth.py`: `register` — обернуть `create`/flush, `IntegrityError`→`UsernameAlreadyExistsError` (`from e`); быстрый pre-check оставить.

**Verification.** `make check`. Ручная: два конкурентных `POST /auth/register` с одинаковым `name` → один 200, второй 409 (а не 500). Кандидат в автотест: мок репозитория бросает `IntegrityError` на create → сервис отдаёт `UsernameAlreadyExistsError`.

---

## Фаза 6 — PDF-экспорт: трансляция отказа + таймаут (F-API-03)

**Цель.** Падение `wkhtmltopdf`/`pdfkit` сейчас всплывает сырым 500 без трансляции и таймаута. На барьере эндпоинта различить ошибку рендера → 502 (внешний инструмент, D-ERR-3) + лог `exc_info`; добавить таймаут на конвертацию. **Числовое значение таймаута → Settings/env (D-ERR-11)** — пересечение с T2 (см. OQ-6).

**Изменения по файлам.**
- `backend/app/api/export.py`: ловить ошибку `pdfkit` → доменное `UpstreamUnavailableError(code="pdf-render-failed", status=502)`; параметризовать таймаут процесса.
- `backend/app/api/routes/artifacts.py`: путь `format=="pdf"` (строки ~71-73) — не глотать, дать всплыть на барьер.

**Verification.** `make check`. Ручная: экспорт артефакта в PDF при сломанном/недоступном `wkhtmltopdf` → 502 problem+json, не сырой 500; превышение таймаута → 504 (если решено мапить timeout туда) или 502 (см. OQ-6). Happy-path PDF не сломан.

---

## Фаза 7 — SSE error-трансляция на роут-барьере (F-API-05)

**Цель.** `_event_generator` в `messages.py` не оборачивает итерацию — исключение по ходу рвёт поток без терминального error-события (статус 200 уже ушёл). Runner (`agent/runner.py:226-241`, трек T3) **уже** транслирует in-graph исключения в `StreamEvent(type="error")` + finally-лог; остаточный риск на роут-барьере — исключения в setup-фазе генератора рана (до его try-блока) и при сериализации (`json.dumps`). План: обернуть итерацию `_event_generator` в try/except → терминальное `data: {"type":"error",...}` + `logger.error(exc_info=True)`. Координация с T3 — чтобы не задвоить error-событие (см. пересечения).

**Изменения по файлам.**
- `backend/app/api/routes/messages.py`: try/except вокруг `async for` в `_event_generator`.

**Verification.** `make check`. Ручная: спровоцировать исключение на старте стрима (например, недоступность зависимости рана) → клиент получает финальное `{"type":"error"}`, не обрыв; лог с `exc_info`. Проверить отсутствие двойного error-события при обычном in-graph сбое (его эмитит runner).

---

## Фаза 8 (под вопросом) — `feedback.py`: сужение `except` + `exc_info` (F-API-04, F-API-07)

**Цель.** Широкий `except Exception → HTTPException(503)` маскирует наши баги (TypeError/AttributeError) под «Observability unavailable». Сузить до сетевых/SDK-ошибок Langfuse (→502/503 через `UpstreamUnavailableError`), непредвиденное → generic-барьер 500; добавить `exc_info`. Принадлежность фазы к T1 — **OQ-5** (файл не в явном списке трека).

**Изменения по файлам.** `backend/app/api/routes/feedback.py`.

**Verification.** `make check`. Curl: сбой Langfuse → 503/502 problem+json; внедрённый баг в handler → 500 (не 503). Логи с `exc_info`.

---

## Файлы трека

Создаёт/меняет (main app):
- `backend/app/services/exceptions.py` — иерархия `AppError` (Фаза 1).
- `backend/app/api/problem.py` — барьерный стек (Фаза 2).
- `backend/app/main.py` — регистрация handlers, generic-500 в `request_id_middleware`, health→503 (Фаза 2).
- `backend/app/services/sphere.py` (Фаза 3).
- `backend/app/services/user_memory.py` (Фаза 3).
- `backend/app/services/mcp_server.py` (Фаза 4).
- `backend/app/services/encryption.py` — `EncryptionError` (Фаза 4, опц. — OQ-7).
- `backend/app/services/url_validator.py` — опц., DNS vs SSRF (Фаза 4 — OQ-1).
- `backend/app/services/auth.py` (Фаза 5).
- `backend/app/api/export.py` (Фаза 6).
- `backend/app/api/routes/artifacts.py` (Фаза 6).
- `backend/app/api/routes/messages.py` (Фаза 7).
- `backend/app/api/routes/feedback.py` — под вопросом (Фаза 8 — OQ-5).
- `backend/app/services/__init__.py` — возможно, обновить экспорт новых исключений (Фаза 1).

---

## Open Questions

- **OQ-1 (статус `validate_url`).** Сейчас невалидный URL → 400. Конвенция: «валидация запроса → 422». Менять 400→422 (изменение контракта для клиента) или ввести `BadRequestError`(400)? Дополнительно F-SVC-10: DNS-сбой и SSRF-«приватный IP» схлопнуты в один ValueError/один статус — развести разными типами/статусами или задокументировать слияние? D-ERR-3 не покрывает. → архитектору.
- **OQ-2 (`MCP_ENCRYPTION_KEY not configured`).** Сейчас 400. Это серверная мисконфигурация, всплывающая клиенту при попытке сохранить api-key. Какой доменный тип/статус (400? 409? 503)? → архитектору.
- **OQ-3 (механизм generic-500 + CORS).** Ловить `Exception` в `request_id_middleware` (ниже CORS) против `add_exception_handler(Exception)` + перестановка CORS в самый внешний слой. Оба дают CORS на 500; план по умолчанию — middleware-перехват (закрывает и лог в `request_id_middleware`). Подтвердить выбор.
- **OQ-4 (AuthError → AppError).** Сворачивать ли `AuthError`-дерево в `AppError` ради единообразия `code`/`status`, или оставить отдельным с локальной обработкой в `routes/auth.py` (текущий эталон F-API-08)? По умолчанию — оставить как есть.
- **OQ-5 (scope `feedback.py`).** F-API-04/F-API-07 — это T1 (API-боundary main app) или выносится (T7-гигиена логов / feat-008 reviewer)? Файл не в явном списке трека.
- **OQ-6 (таймаут PDF — граница T1/T2).** Значение таймаута конвертации → Settings/env (D-ERR-11) — это T2 (config/infra). T1 добавляет try/except + параметр, а Settings-поле и числа заводит T2? И мапить ли таймаут PDF в 504 или в 502? Координация с T2.
- **OQ-7 (объём 🟢-находок).** Включать ли в Фазу 4 опортунистически `EncryptionError` (F-SVC-11) и развод `url_validator` (F-SVC-10), или ограничиться путём B→A и оставить 🟢 на refactor-список?
