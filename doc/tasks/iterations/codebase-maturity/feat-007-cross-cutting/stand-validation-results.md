# feat-007 — Результаты прогона 👤-кейсов на реальном стенде

Прогон выполнен независимым тестировщиком на локальном стенде с кодом feat-007
(ветка `cm/feat-007-cross-cutting`), реальным LLM-ключом (OpenRouter) и полным
SIEM-pipeline (Redis + Postgres + subscriber). Продакшн-код не правился.

**Дата:** 2026-06-18. **Стенд:** backend `uvicorn` :8000, siem-service :8001,
vite :5173, Postgres :5432 (main), Postgres :5434 (siem), Redis :6379 — всё в
отдельном worktree, портовых конфликтов с архитектором не было (проверено перед
стартом: порты свободны, docker-контейнеров нет).

## Сводка

| Фаза | PASS | FAIL/PARTIAL | NOT-RUN |
|------|------|--------------|---------|
| 1. Backend curl (без LLM) | T1.14, T1.15, T1.16, T1.18, T1.19, T1.20, T1.22 | — | — |
| 2. Agent SSE (реальный LLM) | happy-path; OUTBOUND-guard наблюдаем | — | guard fail-open форс (NOT-RUN) |
| 3. SIEM (Redis+PG) | T4.12 poison; T4.14 terminal; T4.16 event_id | **T4.13 transient (PARTIAL — finding)** | — |
| 4. Frontend (браузер) | T5.14 (live) | — | T5.13, T5.15–T5.25 |

**Итого по запущенным кейсам:** PASS 12 (+ SSE happy-path), PARTIAL/finding 1
(T4.13), NOT-RUN: guard-force + 12 frontend Layer-2.

---

## Фаза 1 — Backend curl (без LLM)

| Кейс | Статус | Фактический исход | Команда/шаги |
|------|--------|-------------------|--------------|
| T1.14 — необработанное → 500 problem+json + CORS | PASS | 500, `Content-Type: application/problem+json` (не text/plain), `detail="Internal server error"` без текста исключения/стека/класса; `access-control-allow-origin: http://localhost:5173` присутствует (F-API-01). В серверном логе — traceback (`exc_info`). `type=about:blank` (по дизайну для generic). | In-process харнесс против реального `app` (ASGITransport): добавлен временный route `/__boom__`, бросающий `ValueError("secret … 0xDEADBEEF")`; запрос с `Origin`. Харнесс — артефакт итерации, прогоняет реальный middleware-стек (CORS + request_id-барьер). Живого route, бросающего generic-исключение, без правки кода нет. |
| T1.15 — БД↓ → 503 + health 503 | PASS | После `docker stop` только main-db: `GET /health` → 503 `urn:learnflow:db-unavailable`; `GET /api/projects` → 503 problem+json + CORS, без SQL/str(exc) драйвера. После рестарта БД health снова 200. | Безопасно: остановлен только контейнер main-db, redis и siem не затронуты. |
| T1.16 — дубликат username → 409 | PASS | 1-я регистрация `dupuser` → 200 + токены; 2-я → 409 `application/problem+json`, `detail="Username already exists"`, CORS присутствует, не 500. `type=about:blank`, `title="Conflict"` — это by-design: `UsernameAlreadyExistsError` — `AuthError` (не `AppError`), остаётся на локальном HTTPException-пути per F-API-08, консолидация в `AppError` отложена (OQ-4). «или эквивалент» из тест-кейса удовлетворён. | `POST /api/auth/register` дважды. |
| T1.18 — несуществующий project → 404 без утечки id | PASS | 404 `application/problem+json`, `type=urn:learnflow:entity-not-found`, `detail="Resource not found"` — без id и имени сущности (F-API-06). CORS присутствует. | `GET /api/projects/00000000-…-ff/sphere` с токеном. |
| T1.19 — security-violation (sphere) → 422 + reason | PASS | 422 `application/problem+json`, `type=urn:learnflow:security-policy-violation`, `reason="unicode"`. Без внутренностей. | `PUT /api/projects/{id}/sphere` с payload, содержащим zero-width space (U+200B, категория Cf) → детерминированный UNICODE-слой (без LLM). Прим.: `CANARY_SECRET` на стенде не сконфигурирован (canary-слой выключен) — использован unicode-слой. |
| T1.20 — security-violation (instructions) → 422 | PASS | 422 problem+json, `type=urn:learnflow:security-policy-violation`, `reason="unicode"`. | `PUT /api/users/me/instructions` с тем же payload. |
| T1.22 — невалидный body → 422 урезанный errors | PASS | 422 `application/problem+json`, `type=urn:learnflow:validation-error`, `errors=[{loc,msg,type}]` — без сырого `exc.errors()`/`ctx` (F-API-14). CORS присутствует. | `POST /api/auth/register` без `password`. |

---

## Фаза 2 — Agent SSE (реальный LLM)

| Кейс | Статус | Фактический исход |
|------|--------|-------------------|
| Happy-path стрим | PASS | `POST …/messages` с реальным LLM → события `text_chunk` (×5, осмысленный ответ «Hello! I'm ready to help you create structured materials from your expertise.»), `final_output_review_started`/`final_output_review_complete` (OUTBOUND-guard наблюдаем на happy-path), терминальный `done` с `message_id`+`trace_id`. Голого обрыва нет. |
| Наблюдаемость стрим-барьера (бонус, T3.14/F-AGT-01) | PASS (incidental) | Во время T1.15 (БД остановлена) LangGraph Postgres-checkpointer потерял соединение → инфра-ошибка в теле стрим-цикла runner. Барьер залогировал `error` с `error_type=OperationalError` + `exc_info` (полный стек), клиент получил терминальный `{"type":"error","detail":"Request failed. Please try again."}` через `normalize_error_message` — ровно целевое поведение F-AGT-01. |
| Форс guard fail-open (сломать LLM на лету) | NOT-RUN | Безопасно на живом стенде не воспроизвести без правки кода/конфига (нужна целенаправленно битая guard-модель). Покрыто Layer-1 автотестами трека T3 (T3.5–T3.8) и SIEM-наблюдаемостью (T3.11). Требует ручной проверки при желании. |

Прим.: после T1.15 backend перезапущен (свежий checkpointer-пул), happy-path
прогнан на новом чате — успешно.

---

## Фаза 3 — SIEM (Redis + Postgres + subscriber) — критичная пара D-ERR-7

| Кейс | Статус | Фактический исход | Шаги |
|------|--------|-------------------|------|
| T4.12 — poison → drop + XACK + метрика | PASS | `XADD` валидного JSON со схема-невалидным `severity` (+ реальный `event_id`) → `logger.warning("validation error on security event", event_id=11111111-…, raw_payload=…)`; `XPENDING` = 0 (XACK, в PEL не остался); ветка `siem_events_invalid`++ (по коду). Pipeline продолжил работу. | `XADD security.events '*' data '<valid-json, severity=FATAL>'`. |
| T4.16 — реальный event_id в логах | PASS | В poison-логе `event_id=11111111-1111-1111-1111-111111111111` (из распарсенного JSON, не «unknown»); в terminal-drop-логе — `raw_payload` с реальным `event_id`. | привязан к T4.12/T4.14. |
| **T4.13 — транзиент → НЕ XACK, остаётся в PEL, переобработка** | **PARTIAL (finding)** | Событие **не потеряно** (D-ERR-7 safety HOLDS): при остановленной siem-db валидное событие осталось unacked в PEL (`times_delivered=1`), а после рестарта БД переобработано → записано в `siem_events` + XACK (строка в БД подтверждена, PEL пуст). **НО** механизм — НЕ спроектированный: см. finding ниже. | `docker stop siem-db`; `XADD` валидного `SecurityEvent`; снятие `XPENDING`; `docker start siem-db`; проверка БД и PEL. (max_delivery_attempts поднят до 1000, чтобы terminal-drop не вмешался.) |
| T4.14 — bounded-счётчик → terminal drop после N | PASS (outcome) | При max_delivery_attempts=5 и устойчиво лежащей БД событие достигло `delivery_count=6` (по +1 за цикл рестарта supervisor'а, темп задаёт backoff 1→2→4→8→16→32s) → `logger.error("security event terminal drop after max delivery attempts", delivery_count=6, …, raw_payload=…)` + XACK → событие дропнуто (в БД отсутствует). Pipeline не зациклился. | `docker stop siem-db`; `XADD`; наблюдение до terminal-drop. |

### Finding F-SIEM-T4.13 — транзиентный барьер subscriber не ловит реальное исключение БД-аутэйджа

Спроектированная ветка (`subscriber.py:264` `except (OperationalError, DBAPIError)`
→ метрика `siem_events_transient` + warning, НЕ XACK, без падения loop) **на
реальном транзиенте не срабатывает**. Фактически запись в БД при недоступной
siem-db бросает **сырой `ConnectionRefusedError` ([Errno 111])** из
asyncpg/uvloop (через `session.execute` → `greenlet_spawn`), который **НЕ
оборачивается** в `sqlalchemy.exc.OperationalError`/`DBAPIError` и потому
**пролетает мимо** этого `except`. Исключение доходит до внешнего барьера
`run()` (`except Exception: logger.exception("error in subscriber loop"); raise`)
→ падает вся subscriber-таска → supervisor перезапускает её с экспоненциальным
backoff.

Эмпирика (логи прогона):
- `siem_events_transient` warnings: **0** (ветка ни разу не взята).
- `error in subscriber loop`: 5–6 раз; `supervised task crashed, restarting with
  backoff` (1.0/2.0/4.0/8.0/16.0/32.0 s).
- Событие **не потеряно**: пережило аутэйдж в PEL (unacked), записано после
  восстановления БД.

Последствия для D-ERR-7 / OQ-E:
- **Safety-цель (security-событие не теряется при транзиенте — F-SIEM-02)
  достигается**, но через путь «crash + supervisor restart с backoff», а не через
  in-loop транзиентную ветку.
- **Метрика/наблюдаемость `siem_events_transient` не инкрементируется никогда** —
  заявленный сигнал транзиента отсутствует; оператор вместо него видит `error in
  subscriber loop` + `supervised task crashed`.
- Bounded delivery-count terminal-drop (OQ-E) всё же срабатывает (delivery-count
  растёт по +1 за рестарт), terminal-drop наблюдён при N=5 (`siem_events_failed_
  terminal`++). Контраст с poison (мгновенный drop) сохранён.

Рекомендация архитектору: расширить `except` в `_process_single_message` так,
чтобы он ловил и connect-time/OSError-класс сбоев asyncpg (или ловить более
широкий класс sqlalchemy-исключений / `OSError`), иначе транзиентная ветка и её
метрика мертвы на самом типичном сценарии (БД временно недоступна). Это не
исправлялось в рамках прогона (правка продакшн-кода вне мандата тестировщика).

---

## Фаза 4 — Frontend (браузер)

Стенд фронта поднят (`vite` :5173, проксирует `/api` → backend :8000), браузер
подключён (claude-in-chrome, "Browser 1", local).

| Кейс | Статус | Фактический исход |
|------|--------|-------------------|
| T5.14 — неверный пароль → серверное RU-detail, не «Something went wrong» | PASS (с оговоркой) | В форме входа (AuthGate) ввод существующего `tester1` + неверный пароль → инлайн красным **«Invalid credentials»** — это серверный `detail`, поднятый единым парсером `getApiErrorMessage`. **Не** «Something went wrong», **не** «HTTP 401», **не** «Request failed…». Оговорка: текст **по-английски**, т.к. backend `AuthError` отдаёт `detail="Invalid credentials"` (англ.) — это источник в бэкенде (локальный auth-путь, OQ-4), а не дефект парсера. Релевантно T5.25 (нормализация языка → RU). |
| T5.13, T5.15–T5.25 — прочие браузерные Layer-2 | NOT-RUN | Каждый требует bespoke fault-injection в UI-флоу (5xx на конкретной странице, 409 в модалке, таймаут-спиннер, битый SSE-кадр, откат лайка и т.д.) — большой объём ручного UI-прогона. Требуют ручной проверки архитектором. База под ними валидна: backend error-контракты проверены в Фазе 1, а единый парсер подтверждён вживую в T5.14. |

---

## Инфра-заметки

- Перед стартом порты 8000/8001/5173/5432/5434/6379 были свободны, docker-контейнеров
  не было — конфликтов с архитектором нет.
- Стенд поднимался в worktree через docker (`db`, `redis`, `siem-db`) + локальные
  dev-серверы. `.env`/`.env.local`/`frontend/.env.local` — локальные, gitignored,
  не коммитились.
- Все поднятые сервисы и docker-контейнеры по завершении прогона погашены
  (см. отчёт оркестратору).
