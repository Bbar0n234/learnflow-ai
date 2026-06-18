# test-cases-T1 — Модель ошибок + барьерный стек (main app)

Ручные тест-кейсы, проверяющие ЦЕЛЕВОЕ поведение трека T1 (`plan-T1.md`) после реализации. Норма поведения — `conventions.md` § Обработка ошибок (карта «источник → статус», 3-слойный барьер) и § REST API (форма RFC 9457 problem+json). Решения — `decisions.md` D-ERR-1/2/3 + § Резолюции. Findings — `audit-raw-01-api-boundary.md`, `audit-raw-02-services-db.md`.

Скоуп проверки — только main app (`backend/`). Зеркало барьера в `siem_service/` — трек T4, здесь не проверяется.

## Слои проверки

- **Layer 0** — `make check` (ruff + mypy) проходит.
- **Layer 1** — точечные проверки на уровне функции/handler. Где удобнее ручного — точечный pytest-фрагмент против тестового app (`httpx.ASGITransport` / `TestClient`), иначе ручной разбор. Эти фрагменты не оседают в `backend/tests/` (см. `conventions.md` § Тестирование) — артефакт итерации.
- **Layer 2** — интеграционные `curl` против запущенного сервиса (`make dev` + `make docker-up-db`).
- **Layer 3 / 👤** — требует UI, LLM-ключа, сломанного внешнего бинаря или иного сложного стенда; помечено `👤`.

Общий инвариант для всех Layer 1/2 кейсов (если не сказано иначе): тело ответа — `Content-Type: application/problem+json`, содержит ключи `type`, `title`, `status`, `detail`; НЕ содержит трейсбэка, текста SQL, `str(exc)` драйвера/библиотеки, имени класса исключения, внутренних идентификаторов.

Базовые предусловия Layer 2: backend поднят локально (`make dev`), БД поднята (`make docker-up-db`), `api_prefix = /api`. Где нужен авторизованный запрос — заранее получен access-токен через `POST /api/auth/register` или `POST /api/auth/login` (заголовок `Authorization: Bearer <token>`).

---

## Фаза 1 — иерархия AppError

### T1.1 — Подклассы AppError несут корректные code/status/detail
- **Layer:** 1
- **Предусловие:** реализована иерархия в `backend/app/services/exceptions.py` (Фаза 1).
- **Шаги:** сконструировать каждый подкласс: `NotFoundError`, `ConflictError`, `SecurityPolicyViolationError(reason=...)`, `UpstreamUnavailableError(...)`, `EncryptionError(...)`. Прочитать атрибуты `code`, `status`, `detail` (и `extensions` где есть).
- **Ожидаемо:** соответствие карте D-ERR-3 — NotFound→`status=404`, Conflict→`409`, SecurityPolicyViolation→`422` и `extensions["reason"]` равен переданному, Upstream→503 (или сконфигурированный 502/503), у каждого непустой машинный `code` (kebab-case вида `entity-not-found`, `conflict`, `security-policy-violation`) и безопасный для клиента `detail` без внутренностей. База `AppError` не импортирует `fastapi` и не знает про HTTP (только `code`/`status`/`detail`/`extensions`).

### T1.2 — EntityNotFoundError сохраняет контракт и не протекает id в detail
- **Layer:** 1
- **Предусловие:** `EntityNotFoundError` встроен в иерархию как подкласс `NotFoundError` (Фаза 1).
- **Шаги:** `exc = EntityNotFoundError("Project", 42)`; проверить `__init__(entity, entity_id)` не сломан, прочитать `str(exc)` / `exc.args`, `exc.detail`, `exc.status`, `exc.code`.
- **Ожидаемо:** `str(exc)`/`args` сохраняют `Project`/`42` (для лога), `status=404`, `code="entity-not-found"`, а `detail` — обобщённое сообщение (напр. `"Resource not found"`) БЕЗ id и без имени класса/сущности (F-API-06). Импорт `EntityNotFoundError` из всех 6 мест (`project.py`, `artifact.py`, `chat.py`, `services/__init__.py`, `main.py` и `services/exceptions.py`) не сломан.

---

## Фаза 2 — барьерный стек + регистрация

### T1.3 — AppError → problem+json по exc.status с machine type
- **Layer:** 1
- **Предусловие:** `_app_error_handler` зарегистрирован (Фаза 2).
- **Шаги:** на тестовом app маршрут, бросающий `SecurityPolicyViolationError(reason="x")` и `ConflictError(...)`; вызвать, прочитать статус и тело.
- **Ожидаемо:** HTTP-статус = `exc.status`; тело problem+json с `type` = `urn:learnflow:<code>` (напр. `urn:learnflow:security-policy-violation`), `status` совпадает, extensions проброшены (`reason` для security, `errors` где есть). Нет утечки внутренностей.

### T1.4 — Инфра-исключение БД → 503
- **Layer:** 1
- **Предусловие:** `_infra_exception_handler` на `DBAPIError`/`OperationalError` (Фаза 2).
- **Шаги:** маршрут бросает `sqlalchemy.exc.OperationalError`; вызвать; проверить статус, тело, лог.
- **Ожидаемо:** 503 problem+json (`type` отражает инфра-категорию), в теле нет SQL/`str(exc)` драйвера; в лог записан `exc_info=True` со стеком. `DBAPIError` (родитель) тоже мапится в 503.

### T1.5 — Таймаут зависимости → 504
- **Layer:** 1
- **Предусловие:** инфра-слой мапит `TimeoutError`/`asyncio.TimeoutError`→504 (Фаза 2).
- **Шаги:** маршрут бросает `TimeoutError` (и отдельно `asyncio.TimeoutError`); вызвать.
- **Ожидаемо:** 504 problem+json + `exc_info` в логе; тело без внутренностей.

### T1.6 — generic Exception → 500 problem+json без внутренностей
- **Layer:** 1
- **Предусловие:** last-resort перехват generic `Exception` (Фаза 2, механизм по OQ-3 — перехват в `request_id_middleware` ниже CORS).
- **Шаги:** маршрут бросает `ValueError("secret internal detail 0xDEADBEEF")`; вызвать; прочитать тело и лог.
- **Ожидаемо:** 500, `Content-Type: application/problem+json` (НЕ `text/plain`), `detail` — обобщённое сообщение БЕЗ исходного текста исключения, без стека, без имени класса. В лог записан `exc_info=True` + request-контекст (`request_id`).

### T1.7 — Валидационный handler отдаёт урезанный набор полей
- **Layer:** 1
- **Предусловие:** `_validation_exception_handler` сужен (F-API-14, Фаза 2).
- **Шаги:** на тестовом app отправить невалидный body (нарушение Pydantic-схемы); прочитать тело.
- **Ожидаемо:** 422 problem+json; в `errors`/extensions — только выбранный набор полей (`loc`, `msg`, `type`), БЕЗ сырого `exc.errors()` и без `ctx` с repr внутренних объектов.

---

## Фаза 3 — sphere.py / user_memory.py: путь B→A

### T1.8 — Сервис sphere на injection-вердикте бросает доменное исключение
- **Layer:** 1
- **Предусловие:** `LangGraphSphereService.update` переведён на `SecurityPolicyViolationError` (Фаза 3).
- **Шаги:** вызвать `update` с замоканным guard, возвращающим `Verdict.INJECTION` (с `detection_layer`); перехватить исключение.
- **Ожидаемо:** бросается `SecurityPolicyViolationError` (НЕ `fastapi.HTTPException`); `reason` = значение `detection_layer` (или `ks_write_rest` при отсутствии); security-лог `security_event=True` записан ДО raise. Импорт `fastapi` из модуля удалён (проверяется заодно ruff `F401` в T1.0).

### T1.9 — Сервис user_memory на injection-вердикте бросает доменное исключение
- **Layer:** 1
- **Предусловие:** `update_instructions` переведён на `SecurityPolicyViolationError` (Фаза 3).
- **Шаги:** вызвать `update_instructions` с guard-вердиктом `INJECTION`; перехватить.
- **Ожидаемо:** `SecurityPolicyViolationError` с `reason` = `detection_layer` (или `custom_instructions_write`); security-лог сохранён; `HTTPException`/`fastapi` ушли.

---

## Фаза 4 — mcp_server.py / encryption.py: путь B→A

### T1.10 — _fetch_or_503 транслирует сетевую ошибку в UpstreamUnavailableError с сохранённой причиной
- **Layer:** 1
- **Предусловие:** `_fetch_or_503` починен (F-SVC-03, Фаза 4).
- **Шаги:** вызвать `_fetch_or_503` так, чтобы нижележащий вызов бросил сетевое исключение; перехватить.
- **Ожидаемо:** бросается `UpstreamUnavailableError(code="mcp-unreachable", status=503)`; `__cause__` сохранён (`raise ... from exc`, не `from None`); лог `warning`/`error` с `exc_info=True`; `detail`/extensions клиента НЕ содержат сырой `str(exc)` — только стабильный код.

### T1.11 — MCP injection в метаданных → доменное исключение
- **Layer:** 1
- **Предусловие:** перехват injection metadata в `mcp_server.py` (~317) переведён на `SecurityPolicyViolationError` (Фаза 4).
- **Шаги:** вызвать путь с guard-вердиктом `INJECTION` по `MCP_METADATA`; перехватить.
- **Ожидаемо:** `SecurityPolicyViolationError` (status 422) с корректным `reason`; не `HTTPException`.

### T1.12 — EncryptionService.decrypt транслирует InvalidToken (опц., OQ-7)
- **Layer:** 1
- **Предусловие:** реализован `EncryptionError` (F-SVC-11) — ТОЛЬКО если OQ-7 решён в пользу включения в Фазу 4; иначе кейс не применим.
- **Шаги:** `EncryptionService.decrypt` с битым/несовместимым ciphertext (фейковый `InvalidToken`).
- **Ожидаемо:** бросается доменное `EncryptionError` (не сырой `cryptography.fernet.InvalidToken`); лог с `exc_info`. Статус — по решению OQ-2/OQ-7.

---

## Фаза 5 — auth.register: IntegrityError(unique) → 409

### T1.13 — register транслирует IntegrityError(unique) в UsernameAlreadyExistsError
- **Layer:** 1
- **Предусловие:** `register` оборачивает `create`/flush (F-SVC-01, Фаза 5).
- **Шаги:** замокать репозиторий так, чтобы `create`/flush бросил `sqlalchemy.exc.IntegrityError` (unique на `User.name`); вызвать `register`.
- **Ожидаемо:** бросается `UsernameAlreadyExistsError` (`raise ... from e`), НЕ сырой `IntegrityError`. Быстрый pre-check `get_by_name` сохранён (не удалён).

---

## Layer 2 — интеграционные (curl против запущенного сервиса)

### T1.14 — Необработанное исключение → 500 problem+json (не text/plain) + CORS
- **Layer:** 2
- **Предусловие:** backend поднят; доступен маршрут/условие, гарантированно бросающее необработанное исключение (напр. временный debug-маршрут или известный сбойный путь). Если такого маршрута нет без правки кода — см. 👤-вариант ниже.
- **Шаги:** `curl -i -H 'Origin: http://localhost:5173' <маршрут, бросающий generic Exception>`.
- **Ожидаемо:** статус 500; `Content-Type: application/problem+json` (НЕ `text/plain`, НЕ «Internal Server Error» строкой); тело без стека/SQL; присутствует заголовок `Access-Control-Allow-Origin` (F-API-01 — CORS на 500). В логе сервера — `exc_info` с `request_id`.
- 👤 если для провокации необработанного исключения требуется временная правка кода/специальный стенд — провести при наличии такого маршрута; иначе делегировать человеку.

### T1.15 — Недоступная БД → 503 problem+json и health честно отдаёт 503
- **Layer:** 2
- **Предусловие:** backend поднят, затем БД остановлена (`make docker-up-db`, затем `docker stop` контейнера БД).
- **Шаги:** (a) `curl -i http://localhost:8000/health`; (b) `curl -i` на любой маршрут, делающий запрос к БД (напр. `GET /api/projects` с токеном).
- **Ожидаемо:** оба → 503 `application/problem+json` (НЕ text/plain 500); категория отражает недоступность инфраструктуры; в теле нет `str(exc)`/SQL драйвера. В логе — `exc_info`. После повторного старта БД маршруты снова 200.

### T1.16 — Дубликат username → 409 (регрессия happy-path трансляции)
- **Layer:** 2
- **Предусловие:** backend + БД подняты; username `dupuser` свободен.
- **Шаги:** `POST /api/auth/register` с `{"name":"dupuser","password":"..."}` дважды подряд.
- **Ожидаемо:** первый → 200/201 с токенами; второй → 409 `application/problem+json` (`type=urn:learnflow:conflict` или эквивалент), НЕ 500. Тело без внутренностей.

### T1.17 — TOCTOU: конкурентная регистрация → один 409, не 500
- **Layer:** 2
- **Предусловие:** backend + БД подняты; username `raceuser` свободен.
- **Шаги:** запустить два параллельных `POST /api/auth/register` с одинаковым `name=raceuser` (напр. `curl ... & curl ... & wait`, несколько прогонов чтобы поймать гонку после pre-check).
- **Ожидаемо:** ровно один ответ 200/201, второй — 409 problem+json (а не 500 из сырого `IntegrityError`). Гонка нестабильна — допускается несколько прогонов; критерий: ни одного 500.

### T1.18 — Несуществующий project → 404 problem+json без утечки id
- **Layer:** 2
- **Предусловие:** backend + БД подняты; валидный токен.
- **Шаги:** `curl -i -H 'Authorization: Bearer <token>' http://localhost:8000/api/projects/<несуществующий_id>/sphere` (или любой маршрут по project_id).
- **Ожидаемо:** 404 `application/problem+json`, `type=urn:learnflow:entity-not-found`; `detail` обобщённый, БЕЗ запрошенного id и без имени сущности/класса (F-API-06).

### T1.19 — security-policy violation из sphere → 422 problem+json + reason
- **Layer:** 2
- **Предусловие:** backend + БД подняты; валидный токен; существующий project. Payload, надёжно срабатывающий на ДЕТЕРМИНИРОВАННОМ слое guard (CANARY/UNICODE/FRAGMENT/PAIRED — без LLM-ключа). Если доступен только LLM-классификатор — см. 👤.
- **Шаги:** `PUT /api/projects/<id>/sphere` с body `{"content": "<injection-payload, триггерящий unicode/canary-слой>"}`.
- **Ожидаемо:** 422 `application/problem+json`, `type=urn:learnflow:security-policy-violation`, extension `reason` = слой детекции; в логе — `security_event=True`. Тело без внутренностей.
- 👤 если injection детектируется только LLM-классификатором (нужен LLM-ключ) — делегировать.

### T1.20 — security-policy violation из custom instructions → 422
- **Layer:** 2
- **Предусловие:** как T1.19; валидный токен.
- **Шаги:** `PUT /api/users/me/instructions` с injection-payload (детерминированный слой).
- **Ожидаемо:** 422 problem+json `type=urn:learnflow:security-policy-violation` + `reason`; security-лог записан.
- 👤 если только LLM-слой.

### T1.21 — MCP-сервер с недоступным URL → 503 без сырого str(exc)
- **Layer:** 2
- **Предусловие:** backend + БД подняты; валидный токен; `MCP_ENCRYPTION_KEY` сконфигурирован.
- **Шаги:** создать MCP-сервер с заведомо недоступным URL (`POST /api/users/me/mcp-servers` с `url` на закрытый порт/несуществующий хост), затем вызвать путь, делающий fetch (`_fetch_or_503`).
- **Ожидаемо:** 503 `application/problem+json`, `type=urn:learnflow:mcp-unreachable`; тело НЕ содержит сырой `str(exc)`/reason драйвера; в логе — `exc_info` с сохранённой причиной. (Статус невалидного URL и MCP_ENCRYPTION_KEY-мисконфигурации — по OQ-1/OQ-2, отдельные кейсы не фиксируем до резолюции.)

### T1.22 — Невалидный body → 422 с урезанным errors
- **Layer:** 2
- **Предусловие:** backend поднят.
- **Шаги:** `curl -i` с заведомо невалидным JSON-телом на любой POST/PUT с Pydantic-схемой (напр. `POST /api/auth/register` без `password`).
- **Ожидаемо:** 422 `application/problem+json`; в `errors` только `loc`/`msg`/`type`, без сырого `exc.errors()`/`ctx` (F-API-14).

---

## Фаза 6 — PDF-экспорт (👤)

### T1.23 — Отказ PDF-рендера → 502, не сырой 500
- **Layer:** 2 / 👤
- **Предусловие:** backend + БД подняты; артефакт для экспорта существует; `wkhtmltopdf` сломан/недоступен (напр. PATH без бинаря или подмена на падающий) — требует стенда.
- **Шаги:** `GET`/`POST` экспорта артефакта в PDF (`format=pdf`).
- **Ожидаемо:** 502 `application/problem+json` (`type=urn:learnflow:pdf-render-failed` или эквивалент), НЕ сырой 500; в логе — `exc_info`. Happy-path PDF (исправный бинарь) не сломан.
- 👤 нужен стенд со сломанным внешним бинарём.

### T1.24 — Превышение таймаута PDF-конвертации → 504/502
- **Layer:** 2 / 👤
- **Предусловие:** таймаут конвертации параметризован (Фаза 6); способ заставить `wkhtmltopdf` превысить таймаут (искусственно малый таймаут или зависающий вход). Значение таймаута — Settings/env (пересечение с T2, OQ-6).
- **Шаги:** инициировать PDF-экспорт, превышающий таймаут.
- **Ожидаемо:** запрос завершается ошибкой 504 (или 502 — финальный выбор по OQ-6) problem+json, не висит бесконечно; лог `exc_info`.
- 👤 нужен контроль над таймаутом/зависающим рендером.

---

## Фаза 7 — SSE error-трансляция (👤)

### T1.25 — Ошибка на старте SSE-стрима → терминальное error-событие, не обрыв
- **Layer:** 2 / 👤
- **Предусловие:** backend + БД подняты; LLM/агент-зависимости настроены; способ спровоцировать исключение в setup-фазе генератора рана (до try-блока runner) — напр. недоступность зависимости рана.
- **Шаги:** инициировать SSE-стрим (`POST` сообщения в чат), спровоцировав сбой на старте.
- **Ожидаемо:** клиент получает финальное `data: {"type":"error", ...}` и корректное завершение потока, НЕ голый обрыв соединения; в логе — `exc_info`.
- 👤 нужен LLM-ключ/агентный стенд и контроль над сбоем зависимости.

### T1.26 — Нет двойного error-события при обычном in-graph сбое
- **Layer:** 2 / 👤
- **Предусловие:** как T1.25; способ спровоцировать in-graph исключение (его транслирует runner, трек T3).
- **Шаги:** инициировать стрим с in-graph сбоем.
- **Ожидаемо:** ровно ОДНО терминальное `{"type":"error"}` — роут-барьер не задваивает событие, эмитируемое runner'ом.
- 👤 нужен агентный стенд.

---

## Фаза 8 — feedback.py (под вопросом, OQ-5)

### T1.27 — Сбой Langfuse → 503/502 problem+json
- **Layer:** 2 / 👤
- **Предусловие:** применимо ТОЛЬКО если OQ-5 относит `feedback.py` к T1. Backend поднят; Langfuse недоступен/мокается на сетевую ошибку.
- **Шаги:** `POST` feedback-запрос при недоступном Langfuse.
- **Ожидаемо:** 503/502 `application/problem+json` (через `UpstreamUnavailableError`); лог `warning`/`error` с `exc_info`.
- 👤 нужен контроль над доступностью Langfuse.

### T1.28 — Внедрённый баг в feedback-handler → 500, не ложный 503
- **Layer:** 1 / 👤
- **Предусловие:** применимо только если OQ-5 включает `feedback.py` в T1. `except` сужен до сетевых/SDK-ошибок Langfuse (F-API-04).
- **Шаги:** спровоцировать в handler `TypeError`/`AttributeError` (не сетевую ошибку) — напр. точечным тестом с подменой.
- **Ожидаемо:** ошибка доходит до generic-барьера → 500 (НЕ маскируется под 503 «Observability unavailable»); лог `exc_info`.
- 👤/точечный тест: требует внедрения бага — делается точечным pytest-фрагментом или человеком.

---

## Layer 0 — automated gate

### T1.0 — make check проходит
- **Layer:** 0
- **Предусловие:** все фазы T1 реализованы.
- **Шаги:** `make check` (ruff + mypy) из корня; ожидается также чистый `ruff F401` на `sphere.py`/`user_memory.py`/`mcp_server.py` (импорт `fastapi` удалён).
- **Ожидаемо:** ruff и mypy без ошибок; импорты не сломаны (`EntityNotFoundError` экспортируется из всех мест), `services/__init__.py` экспорт цел, новые исключения видны где импортируются.

---

## Сводка

| Layer | Кейсы | Кол-во |
|-------|-------|--------|
| Layer 0 | T1.0 | 1 |
| Layer 1 | T1.1, T1.2, T1.3, T1.4, T1.5, T1.6, T1.7, T1.8, T1.9, T1.10, T1.11, T1.12, T1.13 | 13 |
| Layer 2 | T1.14, T1.15, T1.16, T1.17, T1.18, T1.19, T1.20, T1.21, T1.22 | 9 |
| Layer 2/3 👤 | T1.23, T1.24, T1.25, T1.26, T1.27, T1.28 | 6 |
| **Всего** | | **29** |

### Кейсы, требующие человека / LLM-ключа / стенда (👤)

- **T1.23** — PDF-рендер 502: нужен сломанный `wkhtmltopdf`.
- **T1.24** — PDF-таймаут 504/502: нужен контроль над таймаутом/зависанием рендера.
- **T1.25** — SSE error на старте стрима: нужен LLM/агентный стенд + контроль сбоя зависимости.
- **T1.26** — отсутствие двойного error-события: агентный стенд.
- **T1.27** — Langfuse-сбой → 503/502: контроль доступности Langfuse (и зависит от OQ-5).
- **T1.28** — внедрённый баг → 500: внедрение бага, точечный тест/человек (зависит от OQ-5).

Условные оговорки в 👤-кейсах T1.14 (если нет маршрута для провокации generic-исключения без правки кода), T1.19/T1.20 (если injection ловится только LLM-классификатором, а не детерминированным слоем guard) — провести автоматически при выполнимости предусловия, иначе делегировать.

### Зависимости от Open Questions

- **T1.12** — применим только при включении `EncryptionError` (OQ-7).
- **T1.21** — статусы невалидного URL / MCP_ENCRYPTION_KEY-мисконфигурации не фиксируются до OQ-1/OQ-2.
- **T1.24** — выбор 504 vs 502 для PDF-таймаута — OQ-6.
- **T1.27/T1.28** — применимы только если OQ-5 относит `feedback.py` к T1.
