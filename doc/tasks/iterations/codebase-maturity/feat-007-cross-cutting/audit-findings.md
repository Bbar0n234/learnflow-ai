# feat-007 — Сводные findings аудита обработки ошибок

Синтез 6 read-only ревьюеров (домены: API boundary, services+DB, agent runtime, resilience, siem-service, frontend). Сырьё по доменам — `audit-raw-01…06.md`. Всего ~67 findings. Аудит вёлся против рубрики решения (5 осей + D1), зафиксированной в обсуждении feat-007.

Главный вывод: контур **в основном зрелый** — есть каркас problem+json, транзакционный барьер сессии, fail-safe телеметрия, наблюдаемая деградация guard на одном из путей. Проблемы кучкуются в **9 кросс-резных тем**; половина из них — один и тот же системный разрыв, проявленный в разных слоях.

---

## Кросс-резные темы

### T1 — 500-gap: нет last-resort Exception-handler (оба сервиса) 🔴
`F-API-01`, `F-SIEM-01`. `register_problem_handlers` в обоих сервисах регистрирует только `StarletteHTTPException` + `RequestValidationError`. Любой неперехваченный `Exception` идёт мимо problem+json через Starlette `ServerErrorMiddleware` → клиенту `text/plain "Internal Server Error"`. Три следствия: (1) нарушен контракт problem+json; (2) `ServerErrorMiddleware` выше `CORSMiddleware` → на 500 нет CORS-заголовков, браузер видит CORS-ошибку; (3) нет гарантированного лога с `exc_info` на барьере. Зеркала идентичны построчно — fix синхронно в обоих.

### T2 — Нет трансляции инфра-исключений в осмысленный статус 🔴
`F-API-02`, `F-SVC-01`, `F-SIEM-06`, `F-AGT` (через runner). БД недоступна → 500 text/plain вместо 503. `IntegrityError` на unique (регистрация юзера; имя SIEM-правила) → 500 вместо 409. Сырые драйверные/ORM-исключения всплывают без перевода в доменное понятие. Нужен слой трансляции на барьере + точечная обработка unique-конфликтов.

### T3 — Неконсистентная модель ошибок в слое сервисов 🟡 (центральная ось)
`F-SVC-02`. Половина сервисов (`project`, `chat`, `artifact`, `auth`) бросает доменные исключения и полагается на барьер; половина (`sphere`, `user_memory`, `mcp_server`) сама бросает `fastapi.HTTPException`, жёстко привязываясь к транспорту. Две несовместимые философии в одном слое. Решение — выбрать одну (каноничнее: сервис бросает доменное исключение, маппинг в статус — единый хендлер).

### T4 — Таймауты на удалённых вызовах отсутствуют 🔴/🟡 (review-and-fix-now)
`F-RES-01…06`, `F-AGT-11`, `F-FE-01`. 6 backend-точек без верхней границы (могут висеть бесконечно): Redis main+SIEM (нет socket_timeout), Postgres main+SIEM (нет statement_timeout), LangGraph checkpointer/store (дёргается на каждом шаге графа), MCP builder из конфига. LLM-вызовы ограничены лишь openai-дефолтом 600s — формально bounded, но для интерактива «висит». Frontend axios без timeout → вечный спиннер. Retry: явной политики нет (openai-дефолты неявны); SIEM-ingestion хорошо (supervised backoff + идемпотентность).

### T5 — Guard fail-open: две дороги деградации, наблюдаема одна (нарушение D1) 🟡
`F-AGT-02/03/04`. Дорога 1 (LLM-исключение) наблюдаема: `security_event=True`, `severity=critical`, `DetectionLayer.GRACEFUL_DEGRADATION`, `exc_info`. Дорога 2 (исчерпание ретраев классификатора, невалидный вывод, `classifier.py:125-134`) — тихая: обычный CLEAN, без security_event/метрики. + дефект разметки: `event_type` зашит как `...INPUT_CLASSIFIER_INJECTION` для всех направлений и противоречит `verdict="clean"`. По D1 обе дороги должны быть наблюдаемы.

### T6 — Silent degradation маскирует реальные сбои 🔴/🟡
`F-SIEM-02` (🔴 — XACK транзиентного сбоя БД стирает retry-страховку Redis Streams → безвозвратная потеря событий безопасности), `F-SVC-04` (широкий except → tools=[] прячет сбой БД), `F-SIEM-05` (неизвестный rule_type молча → ThresholdStrategy). Широкий `except`, возвращающий «пусто», там, где должен всплыть инфра-сбой.

### T7 — Гигиена логирования на error-путях 🟡
`F-API-04/07`, `F-AGT-01`, `F-SVC-03`, `F-SIEM-03/08`. Систематически: лог ошибки без `exc_info`; `raise` без `from e` (или `from None`, рвущий цепочку); барьерные исключения логируются на уровне `warning` вместо `error`; сырой `str(exc)` уходит клиенту. Это прямой вход в reviewer-чек-лист feat-008.

### T8 — Frontend: нет общего парсера problem+json и канала подачи 🟡
`F-FE-02/03/04/09` + `F-FE-13` (эталон). problem+json `detail`/`title` от бэка фактически не читается (пользователю «Request failed with status code 500» / «HTTP 500»). Нет тостов/баннеров вообще, нет глобального `onError`, QueryClient ретраит 4xx. Лекарство уже в кодовой базе — `security-error.ts` читает машинный `type`; его надо обобщить на detail/title и завести единый канал.

### T9 — Расхождение состояния на сбое security-side-effects 🟢
`F-AGT-12`, `F-FE-08`. При сбое `mark_security_blocked` тред не помечается, хотя клиент получил `security_block`; оптимистичный лайк не откатывается. Наблюдаемо, но состояние расходится.

---

## Развилки для архитектора

**Fork A — Result/Either: вводим?**
Свидетельство аудита: кодовая база консистентно на исключениях + Optional, и это сделано хорошо (`F-SVC-09` Optional на чтении → доменное исключение на решении; `F-SVC-08` verify_password «рутинная ветка → bool»; `F-API-11` ожидаемый доменный отказ → Pydantic-результат `success=False`). Рекомендация: **Result/Either-библиотеку НЕ вводить**; зафиксировать «исключения + Optional» как дефолт, плюс «результат-как-значение через Pydantic-объект» для ожидаемых доменных исходов, по которым ветвится непосредственный вызывающий (уже применяется). → решение архитектора.

**Fork B — `store is None` в tools: fail-fast vs graceful.**
Сейчас fail-fast (`RuntimeError` → SSE error → ход рвётся). Рекомендация ревьюера и моя: **оставить fail-fast** (отсутствие стора = поломка деплоя, не рантайм-ветка; маскировка строкой скроет это от оператора), но обеспечить наблюдаемый операторский сигнал (не сливать в `generic`). → решение архитектора.

**Fork C — карта «исключение → статус».**
Зафиксировать конкретную таблицу: `OperationalError/DBAPIError` → 503; `IntegrityError(unique)` → 409; внешний инструмент (wkhtmltopdf, MCP) недоступен → 502/503; таймаут → 504; необработанное → 500; валидация → 422. → утвердить состав.

**Fork D — guard degradation (по D1 уже решено «наблюдаемо», подтвердить scope fix).**
Унифицировать обе дороги под наблюдаемый GRACEFUL_DEGRADATION (security-event + метрика) + канонический `event_type` для деградации + direction по checkpoint. → подтвердить, что чиним в этой итерации.

**Fork E — SIEM-02 (потеря событий): чиним сейчас?**
Это корректностный 🔴 (потеря security-событий на транзиентном сбое БД), не только конвенция. Разделить барьеры: poison→drop+XACK; транзиент→не XACK / dead-letter. → решить scope (feat-007 или отдельный fix).

**Fork F — scope правок feat-007.**
Аудит дал ~67 findings. Это конвенционная итерация — не всё чинить здесь. Предлагаю разнести: **(1) чиним в feat-007** — T1 (500-handler оба сервиса), T4 (таймауты — review-and-fix-now по решению архитектора), T5/D (guard наблюдаемость), плюс точечные 🔴 по согласованию (T2-минимум, T6/SIEM-02); **(2) конвенция + refactor-список на будущее** — T3 (модель ошибок сервисов — большой рефактор), T7 (гигиена логов → частично в feat-008 reviewer), T8 (frontend error-канал — отдельный фронт-объём), T9. → утвердить разбиение.

---

## Эталоны для цитирования в конвенциях
Барьер транзакции `get_db_session` (F-SVC-05); «commit до raise» (F-SVC-06); graceful degradation некритичного + exc_info (F-API-09, F-SVC-07, F-AGT-07/08/09); трансляция upstream→503 с `from e` (F-API-10); таймаут + safe message + результат-как-значение (F-API-11); узкие доменные except в auth (F-API-08); каркас problem+json (F-API-13); normalize_error_message — безопасный минимум клиенту (F-AGT-06); наблюдаемая деградация guard (F-AGT-02); fail-fast core vs degrade вспомогательного в одной ноде (F-AGT-10); supervised + backoff (F-SIEM-G1); poison-event drop (F-SIEM-G2); EventWriter catch/rollback/re-raise (F-SIEM-G3); per-rule isolation (F-SIEM-G4); RFC 9457 type-парсер (F-FE-13); 401→refresh→retry interceptor (F-FE-14); SSE security_block честный error-state (F-FE-15).
