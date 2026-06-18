# Findings — siem-service

Scope: `services/siem-service/siem_service/**` + `packages/siem-contracts`. Ingestion — через Redis Streams (`Subscriber`), не HTTP; HTTP API read/admin-only.

---

### [F-SIEM-01] problem.py 500-gap — идентичен главному сервису 🔴
- Локация: `siem_service/api/problem.py:80-82` (зеркало `backend/app/api/problem.py:85-87`)
- Правило: №4, №7
- Текущее: регистрируются только `StarletteHTTPException` + `RequestValidationError`; generic Exception нет. Сверено построчно — логика байт-в-байт идентична главному (различие только в docstring). Необработанное (напр. OperationalError на `GET /events`) → text/plain 500 мимо problem+json.
- Направление: общий fix с главным — generic Exception-handler + трансляция инфра→503/504. **Делать синхронно в обоих зеркалах.**

### [F-SIEM-02] Pipeline XACK-ит ЛЮБОЙ сбой — транзиентный отказ БД = потеря события безопасности 🔴
- Локация: `siem_service/pipeline/subscriber.py:205-213`
- Правило: №5, №3
- Текущее: `except Exception: logger.exception(...); metrics["errors"]++; xack(...)  # XACK anyway`. ValidationError-ветка выше (`:172-183`) корректно дропает poison+XACK. Но транзиентный инфра-сбой (БД упала на `writer.write`) попадает в широкий барьер и тоже XACK-ается → событие подтверждено, но в БД не записано → потеряно навсегда (стирается retry-страховка Redis PEL/`_read_pending`). Dead-letter нет.
- Направление: разделить барьеры — poison/validation → drop+XACK; транзиент (OperationalError) → НЕ XACK (оставить в PEL) либо dead-letter. Узкий тип вместо общего except.

### [F-SIEM-03] meta_emitter глотает все исключения: нет exc_info, нет метрики 🟡
- Локация: `siem_service/pipeline/meta_emitter.py:58-63`
- Правило: №5, №7
- Текущее: `except Exception as e: logger.error("meta_event_emission_failed", error=str(e))`. meta-события = аудит админских действий над security-системой. При недоступном Redis эмиссия молча проваливается (действие в роуте → 200). Degrade оправдан, но: нет exc_info, нет счётчика дропнутых, stale-комментарий `:45` про идемпотентность неверен (XADD шлёт только `{"data":...}`, event_id внутри JSON).
- Направление: exc_info=True + метрика дропнутых; решить критичность admin-аудита; поправить комментарий.

### [F-SIEM-04] event_id в логах pipeline всегда "unknown" 🟡
- Локация: `siem_service/pipeline/subscriber.py:159` (логи `:176-178`, `:206-210`)
- Правило: №7
- Текущее: `event_id_str = str(payload_dict.get("event_id", "unknown"))`, но stream-запись содержит только `data` (event_id внутри JSON) → всегда "unknown". Оператор не свяжет лог с событием.
- Направление: брать event_id из распарсенного `event_dict`, фолбэк на `message_id`.

### [F-SIEM-05] get_strategy молча подменяет неизвестный rule_type на ThresholdStrategy 🟡
- Локация: `siem_service/correlation/strategies.py:230-237`; схема `domain/schemas.py:153` (`rule_type: str`)
- Правило: №2, №5
- Текущее: `return strategies.get(rule_type, ThresholdStrategy())`. `rule_type`/`severity` — свободные строки (не Literal/enum) → `rule_type="foobr"` пройдёт 422, запишется, выполнится как threshold молча.
- Направление: Literal/enum в `RuleCreateRequest` (→422); в get_strategy для неизвестного — warning или raise.

### [F-SIEM-06] POST /rules: дубликат имени / сбой БД → сырой 500; мёртвая None→500 ветка 🟡
- Локация: `siem_service/api/routes.py:222-226`; `repositories.py:216-237`
- Правило: №4
- Текущее: роут трактует `rule is None` как 500, но create_rule никогда не вернёт None (мёртвый код). Уникальность имени не проверяется (`get_rule_by_name` есть, не используется) → дубликат = IntegrityError → text/plain 500 через gap F-SIEM-01 (должен быть 409).
- Направление: убрать мёртвую ветку; IntegrityError(unique)→409, инфра→503.

### [F-SIEM-07] redis.ping() и engine при старте без таймаута 🟢
- Локация: `siem_service/main.py:51-52`; ср. `infra/db.py:18-22`
- Правило: №6
- Текущее: `from_url(...)` + `ping()` без socket/connect-timeout; fail-fast на критичной зависимости верен, но без таймаута = зависание вместо быстрого отказа.
- Направление: socket_connect_timeout/socket_timeout + connect-таймаут asyncpg. (Дубль с F-RES-01.)

### [F-SIEM-08] _read_pending глотает redis.ResponseError без причины 🟢
- Локация: `siem_service/pipeline/subscriber.py:124-126`
- Правило: №7
- Текущее: `except redis.ResponseError: logger.warning("failed to read pending messages"); return []` — degrade ок, но причина потеряна.
- Направление: добавить `error=str(e)`/exc_info.

---

## Хорошие примеры
- **[F-SIEM-G1] ✅ supervisor.supervised** (`pipeline/supervisor.py:27-43`) — барьер фонового таска: ловит всё кроме CancelledError, exp backoff с потолком, `logger.exception`, сброс backoff. Эталон «барьер + restart с backoff».
- **[F-SIEM-G2] ✅ poison-event** (`subscriber.py:170-183`) — узкий `except ValidationError` → метрика + warning с усечённым payload + XACK. «Дропни одно битое, не вали pipeline».
- **[F-SIEM-G3] ✅ EventWriter.write** (`event_writer.py:62-69`) — catch/rollback/`logger.error(exc_info)`/re-raise → к барьеру subscriber. Throw early, catch late.
- **[F-SIEM-G4] ✅ CorrelationEngine per-rule isolation** (`engine.py:65-75`) — per-rule try/except с exc_info, одно сбойное правило не валит цикл.
- **[F-SIEM-G5] ✅ auth.validate_token** (`infra/auth.py:28-32`) — `jwt.InvalidTokenError → HTTPException(401) from e`, безопасный минимум + причина сохранена.

---

## Итог
8 findings (2 🔴, 4 🟡, 2 🟢) + 5 ✅.
Топ-3: F-SIEM-02 (XACK транзиента → потеря security-событий), F-SIEM-01 (500-gap, консистентен с главным), F-SIEM-03/04 (слепые места наблюдаемости pipeline).
500-gap консистентность: **подтверждена** — оба problem.py идентичны, fix синхронно в обоих.
