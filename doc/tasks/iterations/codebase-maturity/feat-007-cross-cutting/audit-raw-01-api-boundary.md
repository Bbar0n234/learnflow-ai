# Findings — API boundary (main app)

Все локации относительно корня репозитория.

---

### [F-API-01] Нет generic Exception-handler — необработанные ошибки уходят клиенту как text/plain, мимо problem+json и мимо CORS 🔴
- Локация: `backend/app/api/problem.py:85-87`, `backend/app/main.py:545-552`
- Правило рубрики: ось 4 (трансляция на барьере), ось 7 (две аудитории)
- Текущее поведение: регистрируются только три handler'а — `StarletteHTTPException`, `RequestValidationError` (problem.py:86-87) и `EntityNotFoundError` (main.py:548). Generic `Exception`-handler отсутствует.
- Проблема: любой неперехваченный `Exception` проходит мимо problem-handlers через Starlette `ServerErrorMiddleware` и отдаётся клиенту как `text/plain` «Internal Server Error» — выпадает из RFC 9457 problem+json. Три следствия: (1) формат тела не problem+json; (2) `ServerErrorMiddleware` выше `CORSMiddleware` (main.py:510), на 500 не навешиваются CORS-заголовки → браузер видит CORS-ошибку вместо 500; (3) нет гарантированного структурного лога с `exc_info` — `request_id_middleware` (main.py:519-543) не оборачивает `call_next` и не логирует при исключении.
- Направление: last-resort handler для `Exception` → problem_response(status=500, generic detail) + `logger.error(..., exc_info=True)` с request-контекстом.

### [F-API-02] Отказ инфраструктуры (БД недоступна) схлопывается в text/plain 500 вместо 503 🔴
- Локация: `backend/app/api/deps.py:49-58`, `backend/app/main.py:555-559`
- Правило: ось 4 (БД↓→503), ось 2
- Текущее: `get_db_session` делает rollback и re-raise, но сырое инфра-исключение (OperationalError) никем не транслируется; health тоже без обёртки (`SELECT 1`).
- Проблема: при недоступной БД → text/plain 500 вместо 503. Категория дезинформирует.
- Направление: на барьере распознавать OperationalError/DBAPIError → 503; health → честный 503.

### [F-API-03] Падение PDF-экспорта всплывает сырым 500 — без трансляции, таймаута и лога 🟡
- Локация: `backend/app/api/routes/artifacts.py:71-73`, `backend/app/api/export.py:34-39`
- Правило: ось 4 (внешний инструмент→502-503), ось 6 (таймаут)
- Текущее: `convert_md_to_pdf` → `pdfkit.from_string` → внешний бинарь `wkhtmltopdf`; ошибки никем не ловятся, таймаута на процесс нет.
- Направление: на барьере эндпоинта различить ошибку рендера (→502/500 + лог) + таймаут на конвертацию.

### [F-API-04] Широкий `except Exception` в feedback маскирует баги под 503 🟡
- Локация: `backend/app/api/routes/feedback.py:75-79`, `120-124`
- Правило: ось 3 (широкий тип не локально), ось 4 (баг→500)
- Текущее: `except Exception as e: ... raise HTTPException(503, "Observability service unavailable") from e`
- Проблема: оборачивает и реальный отказ Langfuse, и наши баги (TypeError/AttributeError) → всё в 503. Лог warning без exc_info.
- Направление: сузить except до сетевых/SDK-ошибок Langfuse (502/503), непредвиденное → к generic-барьеру 500. Добавить exc_info.

### [F-API-05] Ошибка в SSE-стриме не транслируется в error-событие — клиент получает обрыв потока 🟡
- Локация: `backend/app/api/routes/messages.py:23-29`, `56-63`
- Правило: ось 4, ось 7
- Текущее: `_event_generator` не оборачивает итерацию `service.send_message(...)` в try/except; статус 200 уже отправлен.
- Проблема: исключение по ходу стрима рвёт поток без финального error-события. Подтвердить разделение с `agent_runner` (ему передан `error_messages`).
- Направление: try/except вокруг итерации → терминальное SSE `{"type":"error",...}` + лог exc_info.

### [F-API-06] EntityNotFoundError-handler без машинного type_ и без лога; str(exc) раскрывает имя сущности и id 🟢
- Локация: `backend/app/main.py:548-552`, `backend/app/services/exceptions.py:4-8`
- Правило: ось 7, консистентность problem+json
- Текущее: `problem_response(status=404, detail=str(exc))`, где str(exc) = `"{entity} {entity_id} not found"`.
- Направление: задать `type_=urn:learnflow:entity-not-found`, обобщённый detail без сырого id/имени класса.

### [F-API-07] Лог недоступности Langfuse без exc_info и без детали 🟢
- Локация: `backend/app/api/routes/feedback.py:45-49`
- Правило: ось 7
- Направление: `exc_info=True` в `logger.warning`.

### [F-API-14] Валидационный handler отдаёт сырой `exc.errors()` клиенту 🟢
- Локация: `backend/app/api/problem.py:74-82`
- Правило: ось 7
- Текущее: `errors=jsonable_encoder(exc.errors())` — весь список Pydantic, включая `ctx` (может содержать repr внутренних объектов).
- Направление: осознанно выбрать набор полей (loc/msg/type), не отдавать сырой объект.

---

## Хорошие примеры (для цитирования в конвенциях)

- **[F-API-08] ✅ auth.py** (`routes/auth.py:145-153,182-190,218-233`) — узкие доменные except (`UsernameAlreadyExistsError`→409, `InvalidCredentialsError`→401, `ReplayDetectedError`→401+revoke) локально, где есть контекст; security-лог; `from None` намеренно (не утекают детали проверки). Образец «catch local, узкий тип».
- **[F-API-09] ✅ feedback graceful degradation** (`routes/feedback.py:82-85,126-129`) — запись в Redis некритична (скор уже в Langfuse) → `except Exception` + `logger.warning(exc_info=True)` + проглатывание корректно. Наблюдаемо, не валит ответ. Контраст с F-API-04.
- **[F-API-10] ✅ Трансляция upstream→503 с `from e`** (`routes/feedback.py:43-49,65-79`).
- **[F-API-11] ✅ MCP test-connection** (`routes/mcp_servers.py:100-137`) — явные таймауты (`sse_read_timeout=30`, `timeout=30`); ожидаемый отказ → `TestConnectionResponse(success=False, error=...)` (результат-как-значение) + safe message; сырой str(e) только в лог.
- **[F-API-12] ✅ get_db_session** (`api/deps.py:49-58`) — транзакционный барьер: rollback + re-raise без проглатывания/трансляции. Правильный catch-late.
- **[F-API-13] ✅ problem.py каркас** (`api/problem.py:26-82`) — единая сериализация в problem+json; структурный detail-dict → машинный type + расширения.

---

## Итог
14 findings: 2 🔴, 4 🟡, 2 🟢, 6 ✅.
Топ-3: F-API-01 (нет last-resort Exception-handler), F-API-02 (БД↓→500 вместо 503), F-API-04 (широкий except → ложный 503).
