# plan-T4 — SIEM error handling (siem-service)

Фрагмент плана трека T4 итерации feat-007. Нормы — `conventions.md` § Обработка ошибок (Барьерный стек, SIEM event pipeline), § REST API (problem+json, status codes), § Logging. Решения — `decisions.md` D-ERR-2/D-ERR-3 (барьерный стек — зеркало главного), D-ERR-7 (SIEM потеря событий), D-ERR-10/11. Findings — `audit-raw-05-siem.md` (F-SIEM-01…08). Тест-кейсы как самостоятельные документы пишутся отдельной фазой (Фаза 6); здесь у каждой фазы — подход к verification.

Скоуп — весь siem-сервис, **кроме таймаутов инфры** (redis ping / engine connect — F-SIEM-07, трек T2). Полный путь B→A (перевод всех `HTTPException` siem-роутов на доменные исключения) в этот трек **не входит**: D-ERR-1 ограничивает рефактор путь B→A главным приложением (`backend/`). siem остаётся на `HTTPException`-стиле; T4 чинит только перечисленные findings.

**Зависимость от T1.** Барьер `siem_service/api/problem.py` — построчное зеркало `backend/app/api/problem.py` (подтверждено F-SIEM-01: сейчас идентичны байт-в-байт). Форма handler'ов слоёв 2 (инфра) и 3 (generic) **должна совпасть** с тем, что T1 пишет в главном problem.py. Фаза 1 не может быть финализирована, пока не зафиксирована форма handler'ов T1 (Фаза 2 plan-T1). Мерджить синхронно.

---

## Фаза 1 — Барьерный стек в `siem_service/api/problem.py` (F-SIEM-01)

**Цель.** Добавить недостающие слои перехвата на границе siem-сервиса, зеркально главному (D-ERR-2): слой 2 — инфра-исключения (`DBAPIError`/`OperationalError`→503, timeout→504) + лог `exc_info`; слой 3 — generic `Exception` (last-resort)→500 problem+json без внутренностей + лог `exc_info`. Сейчас регистрируются только `StarletteHTTPException` + `RequestValidationError` → необработанное (например `OperationalError` на `GET /events` при недоступной БД) уходит text/plain 500 мимо problem+json.

Слой 1 (`AppError`) в siem **не появляется в этом треке** — у siem нет иерархии `AppError` (нет `exceptions.py`), а импортировать главную нельзя (отдельный runtime, общего пакета под это нет — зафиксировано в docstring problem.py). siem-роуты бросают `HTTPException(dict-detail)`, который уже корректно разворачивается существующим `_http_exception_handler`. Нужно ли siem собственное мини-дерево `AppError` — см. Open Questions (OQ-1).

**Изменения по файлам.**
- `siem_service/api/problem.py`:
  - `_infra_exception_handler` на `DBAPIError` (включая `OperationalError`); `TimeoutError`/`asyncio.TimeoutError`→504. problem+json + `logger.*(exc_info=True)`. Форму взять у T1.
  - `_unhandled_exception_handler` (generic `Exception`, last-resort)→500 problem+json без `str(exc)`/стека в теле + `logger.error(exc_info=True)`.
  - расширить `register_problem_handlers`.
- `siem_service/main.py`: при необходимости — корректировка регистрации/порядка (см. нюанс CORS ниже).

**Ключевой нюанс — CORS на 500.** В главном приложении T1 решает CORS-on-500 перехватом generic `Exception` в `request_id_middleware` (оно ниже `CORSMiddleware`, ответ проходит обратно через CORS). У siem **нет** request_id middleware (`main.py` — только `CORSMiddleware`). Значит `add_exception_handler(Exception)` в siem попадёт в `ServerErrorMiddleware` выше CORS → 500 без CORS-заголовков (тот же дефект F-API-01, что и в главном). Чем крыть generic 500 в siem, сохраняя зеркальность с T1 (завести аналогичный middleware? принять, что siem read/admin-only и CORS-on-500 для него некритичен?) — Open Questions (OQ-2).

**Verification.** `make check`. Ручная/curl: (a) `make docker-up-db`, поднять siem, остановить БД → `GET /api/security/events` (или иной БД-роут) отдаёт 503 `application/problem+json`, не text/plain; (b) при `Origin`-запросе на упавшем generic-пути проверить наличие/отсутствие `Access-Control-Allow-Origin` (зависит от решения OQ-2); (c) существующие `HTTPException`-пути (404 на несуществующем rule) по-прежнему отдают problem+json. Кандидаты в автотесты: на тестовом siem-app — `DBAPIError`→503, `TimeoutError`→504, generic→500 с пустым телом-без-внутренностей.

---

## Фаза 2 — Разделение барьеров в `subscriber.py` (D-ERR-7, F-SIEM-02/04/08)

**Цель.** Перестать терять security-события при кратковременном сбое БД. Сейчас широкий `except Exception` на строках 205-213 XACK-ит **любой** сбой, включая транзиентный отказ БД на `writer.write` → событие подтверждено, но не записано → потеряно навсегда (стирается retry-страховка Redis PEL). Разделить классы отказа в `_process_single_message`:

- **poison-событие** (`ValidationError` при `model_validate`) → drop + XACK + метрика `siem_events_invalid` + warning с усечённым payload. **Уже корректно** (строки 170-183) — не трогаем, кроме event_id (см. ниже).
- **транзиентный инфра-сбой** (`OperationalError`/`DBAPIError` на записи) → **НЕ XACK** (остаётся в PEL, `_read_pending` переобработает) + метрика `siem_events_transient` + warning `exc_info`. **Не терять** security-событие (F-SIEM-02).
- **bounded-счётчик попыток** — чтобы транзиент не зациклил pipeline. После исчерпания лимита — терминальное действие (drop+XACK с громким `error` + метрика `siem_events_failed_terminal`, т.к. dead-letter признан overkill в D-ERR-7). Лимит (число попыток) — операционная настройка → `Settings`/env (D-ERR-11; новый параметр `SIEM_MAX_DELIVERY_ATTEMPTS` или аналог + правка `.env.example`/`.env.local.example`/`docker-compose.yml`). Где живёт счётчик попыток (in-memory dict по `message_id` в инстансе Subscriber vs Redis delivery-count через `XPENDING`/`XAUTOCLAIM`) и каково терминальное действие при исчерпании — Open Questions (OQ-3).
- **прочее необработанное** (программный баг, не poison и не транзиент) — оставить решение явным: либо узкий перечень транзиентных типов + всё остальное наружу к барьеру `run()` (который сейчас `logger.exception` + `raise` → перезапуск таска супервизором), либо сохранить «дропни одно, не вали pipeline». Уточнить классификацию — OQ-3.

**F-SIEM-04 (event_id="unknown").** `event_id_str = str(payload_dict.get("event_id", "unknown"))` (строка 159) всегда даёт "unknown": stream-запись несёт только поле `data`, event_id внутри JSON. Брать event_id из распарсенного `event_dict` (после `json.loads`), фолбэк на `message_id`. Поправить так, чтобы логи poison/транзиент/terminal несли реальный event_id.

**F-SIEM-08 (`_read_pending`).** `except redis.ResponseError: logger.warning("failed to read pending messages")` (строки 124-126) — degrade ок, но причина потеряна. Добавить `error=str(e)` (или `exc_info=True`).

**Изменения по файлам.**
- `siem_service/pipeline/subscriber.py`: переписать барьер в `_process_single_message` (узкие типы вместо общего except + НЕ-XACK на транзиенте + bounded-счётчик); вынос event_id из `event_dict`; `error=`/`exc_info` в `_read_pending`.
- `siem_service/config.py`: новый `Settings`-параметр лимита попыток (+ синхронная правка четырёх env-мест).

**Verification.** `make check`. Ручная (требует Redis + Postgres через `make docker-up`): (1) **битое событие** — `XADD security.events data='{невалидный JSON или не проходит SecurityEvent}'` → событие дропается + XACK, метрика `siem_events_invalid`++, в PEL не остаётся (`XPENDING`); (2) **транзиент** — подать валидное событие при остановленной БД → событие **остаётся в PEL** (`XPENDING` показывает unacked), метрика `siem_events_transient`++, после поднятия БД `_read_pending` дописывает его; (3) **bounded** — устойчивый отказ БД → после N попыток терминальное действие, pipeline не зациклен. Кандидаты в автотесты: мок `EventWriter.write` бросает `OperationalError` → `xack` НЕ вызван; бросает `ValidationError`-путь → `xack` вызван; счётчик попыток дорастает до лимита → терминальная ветка.

---

## Фаза 3 — `meta_emitter.py`: наблюдаемость деградации (F-SIEM-03)

**Цель.** meta-события — аудит админских действий над security-системой; при недоступном Redis эмиссия сейчас молча проваливается (`except Exception as e: logger.error(..., error=str(e))`, строки 58-63) — действие в роуте всё равно отдаёт 200. Degrade оправдан (admin-аудит некритичен для самого действия), но должен быть наблюдаем:

- `exc_info=True` в логе вместо голого `error=str(e)`.
- счётчик дропнутых meta-событий. MetaEmitter — lifespan-owned синглтон (`get_meta_emitter` из app.state), поэтому может держать `_metrics: defaultdict(int)` по образцу `Subscriber` (метрики siem нигде не экспонируются наружу — это внутренние счётчики, как у Subscriber).
- поправить stale-комментарий строки 45 («XADD ... with event_id as field to ensure idempotency») — неверен: XADD шлёт только `{"data": ...}`, event_id лежит внутри JSON, поля event_id в stream-записи нет. Переписать комментарий на фактическое поведение (или удалить).

**Изменения по файлам.**
- `siem_service/pipeline/meta_emitter.py`: `exc_info=True` + `_metrics` счётчик дропнутых + исправление комментария.

**Verification.** `make check`. Ручная: вызвать админ-действие (`POST /api/security/rules`) при остановленном Redis → действие проходит (200/201), в логе `meta_event_emission_failed` с `exc_info` (стек), счётчик дропнутых++. Кандидат в автотест: мок `redis.xadd` бросает → `emit` не пробрасывает исключение (degrade), лог с `exc_info`, метрика++.

---

## Фаза 4 — Валидация `rule_type`/`severity` + строгий `get_strategy` (F-SIEM-05)

**Цель.** Закрыть тихую подмену неизвестного `rule_type` на `ThresholdStrategy`. Сейчас `rule_type`/`severity` — свободные строки (`domain/schemas.py:153,155` — `Field(...: str)`), а `get_strategy` (`strategies.py:230-237`) делает `strategies.get(rule_type, ThresholdStrategy())` → `rule_type="foobr"` проходит 422-валидацию, пишется в БД и молча исполняется как threshold.

- `RuleCreateRequest.rule_type` → `Literal["threshold", "sequence", "aggregate"]` (невалидное → 422 на барьере валидации, без ручного `if`, по § REST API «валидация выражается схемой»).
- `RuleCreateRequest.severity` → `Literal["info", "warning", "critical"]` (то же множество, что уже используется в `MetaEmitter.emit` и `SecurityEvent.severity` из `siem_contracts` — переиспользовать существующий тип, если он экспортируется, иначе локальный Literal; решить — OQ-4).
- `RuleUpdateRequest` — те же поля nullable → `Literal | None`.
- `get_strategy`: для неизвестного `rule_type` — `warning` + явный отказ вместо тихого fallback. Поскольку схема теперь не пропустит неизвестный тип на create, неизвестное значение в `get_strategy` означает рассинхрон (например, старая запись в БД до ужесточения) → `logger.warning` + поведение (raise vs пропуск правила в движке корреляции) согласовать с per-rule изоляцией `CorrelationEngine` (F-SIEM-G4: одно сбойное правило не валит цикл). Raise здесь поднимется в per-rule try/except движка. Выбор warning-only-skip vs raise — OQ-4.

**Изменения по файлам.**
- `siem_service/domain/schemas.py`: `Literal` на `rule_type`/`severity` в `RuleCreateRequest`/`RuleUpdateRequest`.
- `siem_service/correlation/strategies.py`: `get_strategy` — warning/raise на неизвестном.

**Verification.** `make check` (mypy валидирует Literal). Ручная/curl: `POST /api/security/rules` с `rule_type="foobr"` → 422 problem+json `type=urn:learnflow:validation-error` (не 201); валидный тип → 201. Кандидаты в автотесты: схема отклоняет неизвестный `rule_type`/`severity`; `get_strategy("unknown")` логирует warning / поднимает (по OQ-4).

---

## Фаза 5 — `POST /rules`: мёртвая ветка + дубликат имени → 409 (F-SIEM-06)

**Цель.** Привести создание правила к карте D-ERR-3 (конфликт unique → 409, не 500).

- **Мёртвый код**: роут трактует `rule is None` как 500 (`routes.py:222-226`), но `RuleService.create_rule`/`RuleRepository.create_rule` никогда не возвращают `None` (возврат `RuleResponse`/`CorrelationRule`, не Optional). Убрать ветку. Сигнатуры `create_rule` объявлены как `-> ... | None` без причины — сузить до non-Optional (заодно убирает источник мёртвой проверки).
- **Дубликат имени**: уникальность имени не проверяется (`get_rule_by_name` есть в репозитории, но не используется). Дубликат → `IntegrityError` на flush → сейчас text/plain 500 через gap F-SIEM-01. Должно быть 409. Поймать `IntegrityError` (unique на `CorrelationRule.name`) → 409 problem+json. Поскольку siem не переводится на путь A в этом треке, маппинг делается в siem-стиле (`HTTPException(409, {"error": "rule_name_conflict", ...})` через существующий dict-detail handler), а не через `AppError`. Где ловить (route vs `RuleService.create_rule`) и делать ли дополнительно happy-path pre-check через `get_rule_by_name` (дружелюбный 409 + защита от гонки TOCTOU, как F-SVC-01 в T1) — OQ-5. Вводить ли мини-`ConflictError` в siem завязано на OQ-1 (общая ли иерархия).

**Изменения по файлам.**
- `siem_service/api/routes.py`: убрать `if rule is None` ветку в `create_rule`; добавить `IntegrityError`→409.
- `siem_service/services.py`: сузить возврат `create_rule` до non-Optional; (опц.) перенести ловлю `IntegrityError` сюда — по OQ-5.
- `siem_service/repositories.py`: сузить возврат `create_rule` до non-Optional.

**Verification.** `make check` (mypy — Optional ушёл). Ручная/curl: создать правило с уже занятым `name` → 409 problem+json (не 500/text-plain); создать с новым именем → 201. Кандидат в автотест: мок репозитория бросает `IntegrityError(unique)` на flush → сервис/роут отдаёт 409.

---

## Фаза 6 — Тест-кейсы (ручные + кандидаты автотестов)

**Цель.** Отдельный документ ручных тест-кейсов на затронутые участки (по § Тестирование: основная страховка slice-итерации — ручные тест-кейсы, прогон независимым агентом-тестировщиком; точечные автотесты архивируются в артефакты, не оседают в живом `tests/`).

**Состав.** Сценарии из verification фаз 1-5, в первую очередь два критичных ручных прогона D-ERR-7: **битое событие дропается** (poison → drop+XACK, не в PEL) и **транзиент остаётся в PEL** (БД-сбой → не XACK, переобработка после восстановления). Плюс: 503/504/500 на барьере problem.py; meta-degrade с exc_info; 422 на неизвестный rule_type; 409 на дубликат имени. Кандидаты автотестов перечислены пофазно выше — собрать списком как вход для feat-009.

**Verification.** Документ ревьюится; прогон — независимым агентом-тестировщиком на поднятом стеке (`make docker-up`).

---

## Файлы трека

Меняет (siem-service):
- `services/siem-service/siem_service/api/problem.py` — слои инфра+generic барьера (Фаза 1).
- `services/siem-service/siem_service/main.py` — регистрация/порядок handlers, возможный generic-500/CORS-механизм (Фаза 1 — OQ-2).
- `services/siem-service/siem_service/pipeline/subscriber.py` — разделение барьеров, bounded-счётчик, event_id, `_read_pending` (Фаза 2).
- `services/siem-service/siem_service/config.py` — `Settings`-лимит попыток (Фаза 2).
- `services/siem-service/.env.example`, `.env.local.example`, `docker-compose.yml` — env нового лимита (Фаза 2, atomic с config.py).
- `services/siem-service/siem_service/pipeline/meta_emitter.py` — exc_info + метрика + комментарий (Фаза 3).
- `services/siem-service/siem_service/domain/schemas.py` — Literal rule_type/severity (Фаза 4).
- `services/siem-service/siem_service/correlation/strategies.py` — строгий `get_strategy` (Фаза 4).
- `services/siem-service/siem_service/api/routes.py` — мёртвая ветка + 409 (Фаза 5).
- `services/siem-service/siem_service/services.py` — non-Optional create_rule, (опц.) ловля IntegrityError (Фаза 5).
- `services/siem-service/siem_service/repositories.py` — non-Optional create_rule (Фаза 5).
- документ ручных тест-кейсов в артефактах итерации (Фаза 6).

**Не трогаем** (вне scope T4): таймауты redis ping / engine connect (F-SIEM-07 → T2); путь B→A для остальных siem-`HTTPException` (вне feat-007 scope для siem — D-ERR-1 ограничивает рефактор главным app).

---

## Open Questions

- **OQ-1 (общая ли иерархия `AppError` у siem — ГЛАВНЫЙ вопрос зеркал).** siem — отдельный runtime; общего пакета под `problem.py`/`exceptions.py` нет (зафиксировано в docstring problem.py: «сервисы — самостоятельные runtime'ы, общего пакета под этот модуль нет»). У siem **нет** иерархии `AppError`, и импортировать `backend/app/services/exceptions.py` нельзя. Варианты: (a) siem остаётся без слоя 1 `AppError` — мирроринг ограничивается слоями 2 (инфра) и 3 (generic), роуты продолжают бросать `HTTPException`; (b) завести siem собственное мини-дерево `AppError` (дублирование базы в каждом сервисе); (c) вынести `AppError`+`problem.py` в общий пакет (`packages/`) — крупное архитектурное решение, выходит за scope T4. По умолчанию план идёт по (a). → архитектору.
- **OQ-2 (как держать зеркала problem.py синхронными + CORS-on-500 в siem).** Главный app кроет generic-500 перехватом в `request_id_middleware` (ниже CORS); siem такого middleware не имеет → `add_exception_handler(Exception)` даст 500 без CORS-заголовков. Заводить ли в siem аналогичный middleware ради точной зеркальности, или принять, что siem read/admin-only и CORS-on-500 для него некритичен (тогда зеркала расходятся в механизме, но совпадают в форме тела problem+json)? Как формально фиксировать «синхронность зеркал» при структурном расхождении middleware-стеков двух сервисов? → архитектору. Связано с порядком мерджа: Фаза 1 финализируется после фиксации формы handler'ов в plan-T1 Фаза 2.
- **OQ-3 (механика bounded-счётчика и терминальное действие, D-ERR-7).** Где живёт счётчик попыток: in-memory dict по `message_id` в инстансе `Subscriber` (теряется при рестарте таска — но рестарт и так перечитывает PEL) или Redis delivery-count (`XPENDING`/`XAUTOCLAIM`, переживает рестарт)? Какое терминальное действие при исчерпании лимита, раз dead-letter признан overkill (D-ERR-7): drop+XACK с громким `error`+метрикой (принять потерю после N устойчивых сбоев) или оставлять в PEL бесконечно? И классификация «прочего необработанного» (не poison, не транзиент) — наружу к барьеру `run()` (перезапуск супервизором) или drop? → архитектору.
- **OQ-4 (Literal severity: переиспользовать тип siem_contracts; поведение get_strategy).** `severity` Literal `["info","warning","critical"]` уже фигурирует в `MetaEmitter.emit` и `SecurityEvent` — переиспользовать экспортируемый из `siem_contracts` тип (общий источник) или локальный Literal в schemas (siem-внутренний)? И в `get_strategy` для неизвестного типа — warning+skip (правило не исполняется, изоляция per-rule движка) или raise (поднимется в per-rule try/except)? → архитектору (низкая ставка, можно решить при реализации).
- **OQ-5 (где ловить IntegrityError + нужен ли pre-check).** Ловить unique-violation в роуте (siem-стиль с `HTTPException`) или в `RuleService.create_rule`? Добавлять ли happy-path pre-check через существующий `get_rule_by_name` (дружелюбный 409 + закрывает TOCTOU-гонку, как F-SVC-01) или ограничиться ловлей `IntegrityError`? Завязано на OQ-1 (вводить ли мини-`ConflictError`). → архитектору.

## Пересечения с другими треками

- **T1 (форма problem.py).** Фаза 1 — зеркало главного барьера; форма handler'ов слоёв 2/3 берётся из plan-T1 Фаза 2. Мерджить синхронно; Фаза 1 финализируется после фиксации T1. Слой 1 `AppError` в siem не реплицируется (OQ-1).
- **T2 (siem infra-таймауты).** F-SIEM-07 (redis ping / engine connect без таймаута) — **не T4**, это T2/F-RES-01. Но инфра-исключения, которые ловит барьер Фазы 1 (`OperationalError` от asyncpg, в т.ч. по таймауту) и транзиент-ветка Фазы 2 — порождаются тем, что конфигурирует T2. Числовое значение `SIEM_MAX_DELIVERY_ATTEMPTS` (Фаза 2) — операционная настройка по D-ERR-11, тот же env-механизм, что T2 применяет к таймаутам; согласовать стиль именования env.
- **T3 (vocabulary.py).** plan-T3 Фаза 1 утверждает, что `packages/siem-contracts/siem_contracts/vocabulary.py` «тот же файл правит T4». **По фактическому scope T4 это не так**: T4 не добавляет `EventType` (meta_emitter использует уже существующие `siem.rule.*`), а `rule_type`/`severity` Literal живут в `siem_service/domain/schemas.py`, не в `vocabulary.py`. Если T4 переиспользует severity-тип из `siem_contracts` (OQ-4), это импорт существующего, не правка. Рассинхрон ожиданий с plan-T3 — вынести на сверку: vocabulary.py правит только T3.
