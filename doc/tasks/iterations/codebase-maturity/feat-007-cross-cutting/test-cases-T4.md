# test-cases-T4 — SIEM error handling (siem-service)

Ручные тест-кейсы на **целевое** поведение трека T4 (feat-007). T4 расширен по резолюции
**OQ-C** до полного зеркала главного приложения: siem получает собственную иерархию
`AppError` (`siem_service/.../exceptions.py`) + барьер 3 слоя в `api/problem.py` + перевод
роутов на доменные исключения; в pipeline — разделение барьеров `subscriber.py`
(poison → drop+XACK; транзиент → НЕ XACK, остаётся в PEL; после N попыток → drop+log по
**OQ-E**, delivery-count PEL), наблюдаемость `meta_emitter`, реальный `event_id` в логах,
`Literal` на `rule_type`/`severity`, `POST /rules` → 409 на дубликат + удаление мёртвой ветки.

Нормы: `conventions.md` § Обработка ошибок (Барьерный стек, SIEM event pipeline), § REST API
(problem+json). Решения: `decisions.md` D-ERR-7, OQ-C, OQ-E. Findings: `audit-raw-05-siem.md`.

Зеркало T1: типы problem+json берутся из плана T1 (`type=urn:learnflow:<code>`:
`entity-not-found`→404, `conflict`→409, `security-policy-violation`→422,
`validation-error`→422; инфра→503; timeout→504; generic→500 `about:blank`).

**Легенда.** `👤` — кейс требует полного siem-стенда (Redis + Postgres + запущенный
сервис/subscriber через `make docker-up`), прогон руками независимым тестировщиком.
Кейсы без метки исполнимы дёшево (`make check`, схема-валидация, curl против read-пути /
unit на тестовом app).

---

## Layer 0 — статический gate

### {T4.1} · Layer 0 · `make check` зелёный
- **Предусловие.** Ветка трека T4 со всеми изменениями фаз 1-5; рабочая директория siem-сервиса.
- **Шаги.** `make check` (ruff + mypy на backend-пакетах, включая `services/siem-service`).
- **Ожидаемо.** Проходит без ошибок. В частности: mypy подтверждает `Literal` на
  `rule_type`/`severity`; сужение возврата `create_rule` до non-Optional не даёт
  unreachable/ошибок типов; импорты новой `exceptions.py` верхнеуровневые (нет `PLC0415`);
  нет осиротевших `# type: ignore`/`# noqa` без обоснования.

---

## Layer 1 — доменные исключения, форма problem+json, Literal-валидация

> Исполнимо через curl против запущенного siem с админ-JWT при **доступной** БД, либо
> unit'ом на тестовом FastAPI-app с зарегистрированными handler'ами. Полный стек с
> Redis/subscriber не нужен.

### {T4.2} · Layer 1 · `rule_type` вне Literal → 422 problem+json
- **Предусловие.** siem запущен, БД доступна, валидный админ-токен.
- **Шаги.** `POST /api/security/rules` с телом, где `rule_type="foobr"` (остальные поля
  валидны: `name`, `config`, `severity="warning"`).
- **Ожидаемо.** `422`, `Content-Type: application/problem+json`,
  `type=urn:learnflow:validation-error`, в `errors` — запись про поле `rule_type`. Правило
  **не** создаётся (в БД не появляется), молчаливой подмены на threshold нет. Отказ — на
  барьере валидации схемы, без ручного `if` в роуте.

### {T4.3} · Layer 1 · `severity` вне Literal → 422 problem+json
- **Предусловие.** То же.
- **Шаги.** `POST /api/security/rules` с `severity="fatal"` (rule_type валиден).
- **Ожидаемо.** `422` problem+json `type=urn:learnflow:validation-error`, `errors` указывает
  на `severity`. Аналогично `PATCH /api/security/rules/{id}` с невалидным `severity`/`rule_type`
  → 422 (поля `RuleUpdateRequest` — `Literal | None`).

### {T4.4} · Layer 1 · валидные Literal-значения проходят (негативный контроль)
- **Предусловие.** То же; имя правила свободно.
- **Шаги.** `POST /api/security/rules` с `rule_type` ∈ {`threshold`,`sequence`,`aggregate`}
  и `severity` ∈ {`info`,`warning`,`critical`}.
- **Ожидаемо.** `201`, правило создано; валидация не режет легитимные значения (страховка
  от слишком узкого Literal).

### {T4.5} · Layer 1 · доменное «не найдено» → 404 problem+json
- **Предусловие.** siem запущен, БД доступна, валидный токен.
- **Шаги.** `GET /api/security/rules/{заведомо несуществующий id}`; то же для
  `GET /api/security/alerts/{id}` и `PATCH /api/security/alerts/{id}`.
- **Ожидаемо.** `404`, `application/problem+json`. После перевода роутов на доменные
  исключения (OQ-C) — путь идёт через `NotFoundError`→404-handler (зеркало T1,
  `type=urn:learnflow:entity-not-found`), а не через ad-hoc `HTTPException`. Тело без утечки
  внутренних деталей.

### {T4.6} · Layer 1 · problem+json без утечек внутренностей
- **Предусловие.** Любой кейс T4.2/T4.3/T4.5, перехват полного тела ответа.
- **Шаги.** Снять тело и заголовки 4xx-ответа.
- **Ожидаемо.** Тело — строго `{type, title, status, [detail], …extensions}`; нет
  трассировки стека, нет `str(exc)` драйвера/SQL, нет имён внутренних модулей. `title` —
  стандартная фраза статуса. `Content-Type: application/problem+json` (не
  `application/json`, не `text/plain`).

### {T4.7} · Layer 1 (autotest-кандидат) · `get_strategy` не подменяет неизвестный тип
- **Предусловие.** Unit на `siem_service/correlation/strategies.py`.
- **Шаги.** Вызвать `get_strategy("unknown")`.
- **Ожидаемо.** По резолюции OQ-4: не тихий fallback на `ThresholdStrategy`, а наблюдаемое
  поведение — `logger.warning` + явный отказ (raise / skip правила; конкретика — по выбору
  реализации OQ-4). Известные типы (`threshold`/`sequence`/`aggregate`) возвращают свою
  стратегию. *Кандидат в автотест feat-009.*

---

## Layer 2 — curl / симуляция (полный стек)

### {T4.8} · Layer 2 · 👤 необработанное в siem-роуте → 500 problem+json (не text/plain)
- **Предусловие.** `make docker-up` (siem + Redis + PG). Способ спровоцировать
  необработанное исключение на пути роута (например, внедрённый дефект в обработчик на
  тест-стенде, либо отказ зависимости, не покрытый слоями 1-2).
- **Шаги.** Запрос на сбойный путь с заголовком `Origin`.
- **Ожидаемо.** `500`, `application/problem+json`, тело **без** внутренностей (слой 3 барьера),
  не голый `text/plain`/`Internal Server Error`. В логе — `logger.error(exc_info=True)`.
  По CORS-on-500 (OQ-2): зафиксировать факт — присутствует ли `Access-Control-Allow-Origin`
  (если siem завёл аналог middleware) либо принято отсутствие как осознанный расхождение
  зеркал (siem read/admin-only). Любой исход допустим, но должен совпадать с решением OQ-2.

### {T4.9} · Layer 2 · 👤 БД недоступна → инфра-503 problem+json (не text/plain)
- **Предусловие.** `make docker-up-db`, поднять siem, затем **остановить** Postgres.
- **Шаги.** `GET /api/security/events` (или иной БД-роут) с валидным токеном и `Origin`.
- **Ожидаемо.** `503`, `application/problem+json` (слой 2 барьера: `OperationalError`/
  `DBAPIError`→503), не `text/plain` 500 (закрытие F-SIEM-01). В логе — `exc_info`. Тело без
  `str(exc)` драйвера.

### {T4.10} · Layer 2 (autotest-кандидат) · таймаут зависимости → 504
- **Предусловие.** Unit на тестовом siem-app: handler, поднимающий `TimeoutError`/
  `asyncio.TimeoutError`.
- **Шаги.** Запрос на путь, бросающий таймаут.
- **Ожидаемо.** `504` problem+json (слой 2 барьера), `exc_info` в логе. *Кандидат в автотест
  feat-009 (форма handler'а слоя 2 — зеркало T1).*

### {T4.11} · Layer 2 · 👤 дубликат имени правила → 409 problem+json
- **Предусловие.** `make docker-up`, валидный токен. Существует правило с именем `X`.
- **Шаги.** `POST /api/security/rules` с `name="X"` (валидные Literal-поля).
- **Ожидаемо.** `409`, `application/problem+json` (`ConflictError`→409 по OQ-C, либо
  siem-стиль через `IntegrityError`-ловлю по OQ-5; `type` — `urn:learnflow:conflict`), **не**
  500/`text/plain`. Создание с новым именем → `201`. Мёртвая ветка `if rule is None` → 500
  убрана; при штатном создании она недостижима (проверяется тем, что happy-path даёт 201, а
  конфликт — 409, а не 500).

### {T4.12} · Layer 2 · 👤 poison-событие → drop + XACK + метрика, не остаётся в PEL
- **Предусловие.** `make docker-up`, subscriber запущен и читает `security.events`.
- **Шаги.** `XADD security.events '*' data '<битый JSON или payload, не проходящий
  SecurityEvent>'`. Дождаться обработки. Снять `XPENDING security.events siem-readers` и
  `Subscriber.get_metrics()`.
- **Ожидаемо.** Событие **дропнуто** + **XACK** (в PEL не остаётся — `XPENDING` не показывает
  его unacked). Метрика `siem_events_invalid`++. В логе — `warning` с усечённым `raw_payload`.
  Pipeline продолжает работать. (Поведение poison-ветки сохранено как было — F-SIEM-G2.)

### {T4.13} · Layer 2 · 👤 транзиентный сбой БД на записи → НЕ XACK, переобработка после восстановления
- **Предусловие.** `make docker-up`, subscriber запущен. Возможность кратковременно
  **остановить** Postgres, оставив Redis живым.
- **Шаги.** Остановить Postgres. `XADD security.events '*' data '<валидный SecurityEvent>'`.
  Дождаться попытки обработки. Снять `XPENDING` и `siem_events_transient`. Затем **поднять**
  Postgres и дождаться следующего прохода `_read_pending`.
- **Ожидаемо.** Пока БД лежит: событие **НЕ XACK** — остаётся в PEL (`XPENDING` показывает
  unacked-сообщение), метрика `siem_events_transient`++, в логе `warning`/`exc_info` про
  транзиент. Security-событие **не потеряно** (закрытие F-SIEM-02). После поднятия БД
  `_read_pending` переобрабатывает: событие записывается в БД и XACK-ается, из PEL исчезает.
  Ключевой контраст с T4.12: транзиент в PEL остаётся, poison — нет.

### {T4.14} · Layer 2 · 👤 bounded-счётчик: устойчивый сбой → после N попыток drop+log, pipeline не зациклен
- **Предусловие.** `make docker-up`, subscriber запущен. `SIEM_MAX_DELIVERY_ATTEMPTS`
  (≈5 по OQ-E) задан в env. Постоянный отказ записи (например, Postgres стоит долго, либо
  воспроизводимый сбой `EventWriter.write`).
- **Шаги.** `XADD` валидного события при устойчивом сбое БД. Наблюдать переобработки события
  через `_read_pending` (delivery-count PEL растёт). Дождаться исчерпания лимита.
- **Ожидаемо.** Событие переобрабатывается ограниченное число раз (delivery-count PEL,
  не in-memory). По достижении `SIEM_MAX_DELIVERY_ATTEMPTS` — терминальное действие:
  drop + XACK + `logger.error` с payload (метрика `siem_events_failed_terminal` или аналог).
  Pipeline не зацикливается на этом событии — следующие события обрабатываются. (OQ-E:
  dead-letter не вводится, принятая потеря после N устойчивых сбоев.)

### {T4.15} · Layer 2 · 👤 meta-emitter degrade при недоступном Redis → действие проходит, лог наблюдаем
- **Предусловие.** `make docker-up`, БД доступна. Способ сделать Redis недоступным для
  `MetaEmitter.xadd` (остановить Redis после старта роутов, либо стенд с отдельным Redis).
- **Шаги.** Админ-действие `POST /api/security/rules` (валидное) при недоступном Redis.
- **Ожидаемо.** Действие **проходит** (`201`, правило в БД) — degrade оправдан, эмиссия
  meta-аудита некритична для самого действия. В логе — `meta_event_emission_failed` с
  `exc_info=True` (стек), не голый `error=str(e)` (закрытие F-SIEM-03). Счётчик дропнутых
  meta-событий в `MetaEmitter._metrics`++. Исключение из `emit` наружу **не** пробрасывается.

### {T4.16} · Layer 2 · 👤 реальный `event_id` в логах pipeline (не "unknown")
- **Предусловие.** Привязан к прогонам T4.12 (poison) и T4.13 (транзиент). Событие несёт
  известный `event_id` внутри JSON `data`.
- **Шаги.** Снять логи poison/транзиент/terminal-веток.
- **Ожидаемо.** В логах `event_id` равен реальному значению из распарсенного `event_dict`,
  фолбэк на `message_id` — не константа `"unknown"` (закрытие F-SIEM-04). Оператор связывает
  лог с событием.

### {T4.17} · Layer 2 · 👤 `_read_pending` логирует причину `ResponseError`
- **Предусловие.** `make docker-up`. Способ вызвать `redis.ResponseError` на чтении pending
  (например, повреждённая/несовместимая группа — стенд-специфично; допустимо проверить
  только наличие `error=`/`exc_info` в ветке логирования при ревью кода, если воспроизведение
  затруднено).
- **Шаги.** Спровоцировать `ResponseError` в `_read_pending`.
- **Ожидаемо.** `logger.warning("failed to read pending messages", error=str(e))` (или
  `exc_info=True`) — причина не теряется (закрытие F-SIEM-08); degrade сохранён (возврат `[]`).

---

## Gate

- **Layer 0** обязателен и блокирующий: {T4.1} `make check` зелёный — без него трек не
  считается готовым к прогону.
- **Layer 1** ({T4.2}–{T4.7}) — прогоняется при доступной БД + админ-токене; быстрый,
  не требует Redis/subscriber. {T4.7} и {T4.10} вынесены как автотест-кандидаты в feat-009.
- **Layer 2** ({T4.8}–{T4.17}) — основная страховка D-ERR-7; прогон на полном стенде
  `make docker-up`. Критичная пара: **{T4.12} poison дропается / {T4.13} транзиент остаётся
  в PEL** — именно она доказывает, что починена потеря security-событий (F-SIEM-02).
- **Зависимость от T1.** Форма handler'ов слоёв 2/3 и иерархия `AppError` siem — зеркало T1;
  кейсы T4.5/T4.8/T4.9/T4.10/T4.11 валидны только после фиксации формы в plan-T1 Фаза 2.
  Если CORS-on-500 (OQ-2) и место ловли `IntegrityError` (OQ-5) ещё не утверждены —
  зафиксировать фактический исход, не помечая как провал.

## Кандидаты в автотесты (вход для feat-009)

- Схема отклоняет неизвестный `rule_type`/`severity` (→422) — {T4.2}/{T4.3}.
- `get_strategy("unknown")` → warning/raise, не тихий threshold — {T4.7}.
- Handler-на-слой на тестовом app: `AppError`→статус, `DBAPIError`→503, `TimeoutError`→504,
  generic→500 с пустым телом-без-внутренностей — {T4.8}/{T4.9}/{T4.10}.
- Мок репозитория бросает `IntegrityError(unique)` на flush → сервис/роут отдаёт 409 —
  {T4.11}.
- Мок `EventWriter.write` бросает `OperationalError` → `xack` **НЕ** вызван; бросает
  `ValidationError`-путь → `xack` вызван; delivery-count дорастает до лимита → терминальная
  ветка — {T4.12}/{T4.13}/{T4.14}.
- Мок `redis.xadd` в `MetaEmitter.emit` бросает → исключение не пробрасывается, лог с
  `exc_info`, метрика++ — {T4.15}.

## 👤-список (требуют полного siem-стенда Redis + PG)

{T4.8}, {T4.9}, {T4.11}, {T4.12}, {T4.13}, {T4.14}, {T4.15}, {T4.16}, {T4.17} — 9 кейсов.
