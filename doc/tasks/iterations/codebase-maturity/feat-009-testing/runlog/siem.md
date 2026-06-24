# S8 — SIEM + contracts · run-log

Скоуп: парсинг/ингест событий (siem-service), целостность словаря и сериализация
(siem-contracts), cross-side совпадение словаря эмиттер ↔ консьюмер. Unit +
contract. Инфра Ф2b не трогалась — используются её фикстуры (testcontainers PG,
транзакционный откат) и общий пакет `learnflow_testing`.

## Файлы

Тесты (только свои подпапки):
- `services/siem-service/tests/pipeline/fakes.py` — расширен (был от прерванного
  прогона: `FakeStreamRedis`, `CountingSessionFactory`). Добавлены: `make_event`,
  `producer_envelope`, `raw_message`/`event_message`, `make_settings`,
  `make_subscriber` (мост duck-typed fake Redis → концретный `redis.Redis` через
  один `cast`), `FailingSessionFactory` + `_RaisingSession` (транзиентный сбой БД).
- `services/siem-service/tests/pipeline/test_subscriber_ingest.py` — поведение
  ингеста через публичный `Subscriber.run()`.
- `services/siem-service/tests/pipeline/test_event_writer.py` — `EventWriter`
  против живого PG (дедуп, JSONB-маппинг).
- `services/siem-service/tests/pipeline/test_cross_side_contract.py` — cross-side
  словарь.
- `packages/siem-contracts/tests/__init__.py`
- `packages/siem-contracts/tests/test_vocabulary.py` — целостность словаря.
- `packages/siem-contracts/tests/test_events_serialization.py` — wire-контракт
  `SecurityEvent`.

Прод НЕ правился.

## Покрытые поведения

### Парсинг / ингест (subscriber, sociable-unit на фейк-Redis + живой PG)
- Валидное событие → распарсено, записано в PG, XACK, метрика `*_ingested`.
- Идентификаторы продьюсера (`exclude_none`) приземляются в JSONB как есть.
- Дубль `event_id` (две доставки) → одна строка, обе ACK, метрика `*_duplicate`
  (идемпотентность через `ON CONFLICT DO NOTHING`).
- **Poison** (ValidationError): невалидная severity / неизвестный `event_type` /
  отсутствие обязательных полей → drop + XACK + метрика `*_invalid`, сессия записи
  НЕ открывается (`factory.calls == 0`).
- **Terminal drop**: delivery_count > `max_delivery_attempts` → drop + XACK +
  метрика `*_failed_terminal`, до парсинга/БД.
- **Transient infra** (no XACK, остаётся в PEL): SQLAlchemy `OperationalError` на
  `execute` И сырой connect-time `ConnectionRefusedError` при открытии сессии
  (кейс F-SIEM-T4.13, asyncpg не оборачивается в SQLAlchemy) → метрика
  `*_transient`, нет ACK.
- **Малформед не-JSON payload**: фактическое поведение — re-raise в supervisor
  barrier, НЕ ACK (см. «Баги для Ф5» — асимметрия с poison).

### EventWriter (repository-integration, живой PG)
- Новое событие → `True`, поля персистятся (severity, identifiers, маппинг
  Pydantic `metadata` → колонка `event_metadata`).
- Повтор `event_id` → `False`, одна строка.
- Коллизия `event_id` с другим payload → первая строка сохраняется (DO NOTHING,
  не last-write-wins).

### Целостность словаря (siem-contracts)
- `EventType` Literal ⇔ модульные UPPERCASE-константы — точное совпадение
  множеств (главный страж дрейфа).
- Нет дублей значений (Literal и константы).
- Иерархический нейминг `<domain>.<subject>.<outcome>` (≥3 сегмента) по regex.
- Каждая константа ре-экспортируется из `siem_contracts.__all__` и доступна на
  пакете; `EventType` тоже экспортирован.

### Сериализация SecurityEvent (wire-контракт)
- Round-trip `model_dump_json` → `model_validate_json` лосслесс (UUID, datetime,
  identifiers, metadata).
- `identifiers.model_dump(exclude_none=True)` роняет None — как в EventWriter.
- Дефолты: identifiers пустой, metadata `{}`.
- Reject: неизвестный `event_type`, невалидная severity, не-UUID `event_id`,
  отсутствие обязательных полей (на эти ветки опирается poison-drop консьюмера).

### Cross-side словарь (эмиттер ↔ консьюмер)
- Консьюмер (`subscriber`, `event_writer`) ссылается на ТОТ ЖЕ объект
  `siem_contracts.SecurityEvent` — не форк.
- Каждый член канонического словаря проходит валидацию `SecurityEvent` (единственный
  гейт консьюмера) — консьюмер знает весь словарь продьюсера.
- Эмиттер (backend `auth.py`, `guard.py`) НЕ хардкодит `event_type=`-литералы вне
  словаря и берёт константы `from siem_contracts` — проверка чтением исходника
  (backend не импортируется из siem-test-окружения; см. «Решения»).

## Тесты + результат
- `make test` (siem-часть): **46 passed** (44 новых S8 + 2 существующих smoke/drift).
- `packages/siem-contracts/tests` (вне `make test`, прогон напрямую через
  `uv run --package siem-service pytest ... packages/siem-contracts/tests`):
  **64 passed**.
- `uv run ruff check` (свои файлы) — clean.
- `uv run mypy services/siem-service/` — Success, no issues (43 files).
- Регрессий нет: полный `make test` — backend 518 passed / siem 46 passed.

## Решения
- **Cross-side без dual-import.** В окружении `uv run --package siem-service`
  пакет `app` (backend-эмиттер) НЕ импортируется (backend не зависимость
  siem-service). Поэтому cross-side собран без одновременного импорта обеих
  сторон: (1) рантайм-проверка, что консьюмер использует общий объект контракта;
  (2) валидация каждого члена словаря; (3) AST-скан исходника эмиттера (чтение
  файла по пути от repo-root, без импорта `app`) на хардкод и на источник
  констант. Это ловит реальный дрейф «одна сторона разъехалась», оставаясь в
  границах импортируемости.
- **Duck-typing fake Redis.** `Subscriber.__init__` типизирует `redis_client` как
  конкретный `redis.Redis` (не Protocol). Фейк — структурный заменитель;
  один `cast` в `make_subscriber` вместо россыпи `# type: ignore` (testing.md
  § Дубли).
- **Стоп остановки loop.** Бесконечный `Subscriber.run()` останавливается публично
  — фейк-Redis бросает `CancelledError` после скриптованной пачки; `_drain`
  глушит её для пост-условий.

## Баги для Ф5
1. **Малформед не-JSON payload крашит консьюмер-таск (асимметрия с poison).**
   `_process_single_message`: `json.loads` падает с `JSONDecodeError` ДО
   `model_validate`, исключение не ловится внутренним try (он только вокруг
   ValidationError) и попадает в внешний `except` → `is_transient_db_error` ложь →
   **re-raise** в supervisor barrier. Schema-невалидный JSON корректно
   poison-дропается (drop+XACK+`*_invalid`), а вот payload, который вообще не JSON,
   трактуется как «неожиданный баг» и роняет таск → supervisor рестартит → то же
   сообщение перечитывается из PEL → краш-луп, ограниченный только
   `max_delivery_attempts` (terminal drop). Ожидание: невалидный JSON — такой же
   poison, как и невалидная схема (drop+XACK сразу). Тест
   `test_subscriber_malformed_non_json_payload_is_not_acked` фиксирует ФАКТИЧЕСКОЕ
   поведение (re-raise, no ACK), не утверждая его корректность.
2. **`_is_known_event_type` — мёртвая ветка (vocabulary-soft mode).** Метод всегда
   возвращает `True`, а `SecurityEvent.event_type` — строгий `Literal`, поэтому
   неизвестный тип отсекается ValidationError'ом (poison) ещё ДО проверки
   `_is_known_event_type`. Ветка soft-mode и метрика `siem_unknown_event_type`
   недостижимы для реально неизвестного типа. Не баг поведения, но мёртвый/
   вводящий в заблуждение код — кандидат на удаление либо на ослабление типа
   `event_type` до `str`, если soft-mode действительно нужен.

## Непокрытое и почему
- **`backend/app/repositories/trace_store.py` — НЕ покрыт (блокер).** Прод
  Redis-backed (Redis HASH `trace:{thread_id}`, feedback-ключи), а НЕ PG — в
  отличие от формулировки скоупа «integration против живого PG». Тест требовал бы
  (а) Redis-фикстуры, которой замороженный харнесс Ф2b не предоставляет (есть
  только `postgres_container`), и (б) записи в `backend/tests/` — вне моих
  разрешённых путей (это территория backend-скоупов S1–S7). Дисциплина путей +
  отсутствие Redis-инфры → не покрываю, эскалирую (см. «Блокеры»).
- **`packages/siem-contracts/tests` вне `make test`.** Цель `test` гоняет только
  `backend/tests` и `services/siem-service/tests`; библиотечные contract-тесты не
  собираются CI-гейтом. Makefile заморожен — не правлю. Тесты зелёные при прямом
  прогоне. Частичная подстраховка в гейте: cross-side-набор (в siem-suite, ВНУТРИ
  `make test`) уже проверяет identity контракта, валидацию всего словаря и что
  эмиттер тянет константы из `siem_contracts` со сверкой значений против Literal —
  так что гейт не слеп к дрейфу, но внутренний страж «Literal ⇔ константы» живёт
  только в библиотечных тестах. См. «Блокеры».
- **Correlation engine / API routes / supervisor / meta_emitter** — вне скоупа S8
  (парсинг/ингест + словарь). Не трогал.

## Блокеры
1. **trace_store**: расхождение формулировки скоупа («PG») с реальностью (Redis) +
   нет Redis-фикстуры в замороженном харнессе + код вне разрешённых путей записи.
   Нужно решение архитектора: (а) добавить Redis-фикстуру в харнесс (Ф2b/Ф5) и
   (б) определить владельца теста (backend-скоуп vs S8). Прод не правил.
2. **CI-гейт для siem-contracts**: `make test` не собирает
   `packages/siem-contracts/tests`. Makefile заморожен → нужна цель/правка в Ф5–Ф6
   (добавить прогон библиотечных тестов в гейт), чтобы страж «Literal ⇔ константы»
   попал под ratchet.
