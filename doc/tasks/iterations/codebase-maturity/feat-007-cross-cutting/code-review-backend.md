# Code Review — feat-007 backend (main app, без agent/siem)

Ревью diff `develop...HEAD` по доменам main app: `backend/app/api`, `backend/app/services`,
`backend/app/infra`, `backend/app/config.py`, `backend/app/main.py`. Семантические замечания
по severity; форматирование оставлено линтерам. agent-runtime и siem-service — вне домена
(ревьюит другой агент).

## Summary

- **blocker: 2**
- **nit: 2**
- **nice-to-have: 2**

Барьерный стек корректен: `AppError`→доменный статус, `DBAPIError`→503, `TimeoutError`/
`asyncio.TimeoutError`→504, generic→500 в `request_id_middleware` (ниже CORS — CORS на 500
получает заголовки). problem+json не утекает стек/SQL/`str(exc)`: `_app_error_handler` отдаёт
только client-safe `detail`+extensions; `_validation_exception_handler` сужен до `loc`/`msg`/
`type`; `EntityNotFoundError.detail`="Resource not found" (id только в `args`/логе). Прямые
`raise HTTPException` из доменных сервисов вычищены (`sphere`, `user_memory`, `mcp_server`,
`url_validator` — на `AppError`; остаток `HTTPException` в `routes/feedback.py` легитимен —
это transport-слой роута). `raise X from e` и `exc_info` соблюдены в `mcp_server`, `feedback`,
`encryption`, `auth`. Таймауты читаются из `Settings` (Redis/PG/MCP/LLM); `statement_timeout`
per-statement через libpq `options`, `idle_in_transaction_session_timeout` НЕ введён. Логирование
— structlog keyword-args + `exc_info=True`.

Две дыры в PDF-экспорте (см. blocker'ы): проброшенный из `Settings` таймаут на деле не
применяется к `wkhtmltopdf`, и путь отказа 502 не пишет лог.

## Замечания

| Severity | Файл:строка | Замечание | Предложение |
|----------|-------------|-----------|-------------|
| blocker | `backend/app/api/export.py:29,41-45` | Параметр `timeout` принимается и прокидывается из `Settings.pdf_conversion_timeout_seconds` через `artifacts.py` (`functools.partial`), но **внутри `convert_md_to_pdf` нигде не используется** — `pdfkit.from_string` вызывается только с `options={"javascript-delay": "5000"}`. Блокирующий subprocess `wkhtmltopdf` остаётся без таймаута и может висеть бесконечно, занимая worker-thread `anyio.to_thread` (пул ~40); серия зависаний → исчерпание пула → стопорятся все блокирующие вызовы, включая argon2-хеширование паролей. Нарушает conventions § Таймауты и retry («каждый вызов ненадёжной зависимости имеет таймаут… дефолты, висящие вечно, считаются багом»); knob создаёт ложное ощущение защиты. | `pdfkit`/`wkhtmltopdf` своего timeout-флага не имеют → завернуть вызов в реальный механизм (например `subprocess`-таймаут через own `Configuration`/обёртку или ограничение на уровне процесса) и применить `timeout`; либо, если таймаут технически не реализуем, убрать мёртвый параметр и зафиксировать ограничение как known-issue для архитектора, а не плодить нефункциональный knob. |
| blocker | `backend/app/api/export.py:46-51` | Отказ рендера PDF → `UpstreamUnavailableError(502)` бросается **без какого-либо лога**: в модуле нет `logger`/`structlog`, а `_app_error_handler` 5xx-`AppError` не логирует. В проде поломка PDF-экспорта (502 — серверный отказ внешнего инструмента) не оставляет следа с `exc_info`. Нарушает conventions § Обработка ошибок («Исключение наблюдаемо: причина сохраняется `raise X from e`, лог с `exc_info`»). Для контраста MCP/Langfuse-пути (`mcp_server._fetch_or_503`, `feedback`) логируют `exc_info` на throw-site. | Логировать на throw-site (`logger.error("pdf render failed", exc_info=True)` перед raise) — единообразно с MCP/Langfuse; либо централизованно логировать `AppError` со `status >= 500` в `_app_error_handler` (покроет все `UpstreamUnavailableError` единым местом). |
| nit | `backend/app/api/problem.py:164-165` | Двойная регистрация `TimeoutError` и `asyncio.TimeoutError`, при том что соседний комментарий сам констатирует: `asyncio.TimeoutError` — подкласс `TimeoutError` в Python 3.11+, регистрация `TimeoutError` уже покрывает оба. Строка 165 избыточна. | Убрать `app.add_exception_handler(asyncio.TimeoutError, ...)` (строка 165); комментарий-обоснование оставить. |
| nit | `backend/app/api/routes/feedback.py:78,129` | Кортеж `except (httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError)` содержит вложенные типы: `httpx.TimeoutException` ⊂ `httpx.HTTPError`, `ConnectionError` ⊂ `OSError`. Перехват корректен, но два члена избыточны и вводят в заблуждение о реальном множестве. | Сузить до `(httpx.HTTPError, OSError)`. |
| nice-to-have | `backend/app/config.py:70,74` | В `langgraph_database_url` Postgres-`connect_timeout` выводится из `redis_socket_connect_timeout`. Это связь-ловушка: правка `REDIS_SOCKET_CONNECT_TIMEOUT` молча меняет таймаут подключения к Postgres/LangGraph. Зафиксировано как резолюция OQ-2, но семантическая связанность остаётся неочевидной. | Завести отдельное поле (напр. `db_connect_timeout_seconds`) или переиспользовать `db_*`-нэйминг, чтобы knob не имел скрытого побочного эффекта на чужую подсистему. |
| nice-to-have | `backend/app/api/problem.py:160-167` | Новые `# type: ignore[arg-type]` на `add_exception_handler` без поясняющего комментария (conventions § Инструменты качества: «никаких слепых подавлений без обоснования»). Это известное ограничение типизации FastAPI и согласуется с пред-существующей строкой `StarletteHTTPException`, поэтому риска нет — но обоснование в коде отсутствует. | Один общий комментарий над блоком: причина ignore — узкая сигнатура handler vs `add_exception_handler` в типах FastAPI. |

## Blocker без прецедента в conventions

Нет. Оба blocker'а опираются на прямые нормы `conventions.md` § «Обработка ошибок» (наблюдаемость
исключений, `exc_info`) и § «Таймауты и retry» (каждый вызов ненадёжной зависимости имеет таймаут).
