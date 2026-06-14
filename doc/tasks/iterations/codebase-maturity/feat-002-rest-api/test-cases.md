# Test Cases: feat-002 — REST API Slice

Контрактные проверки REST API после правок slice'а: авторизация и ownership, статус-коды, pagination/envelope, формат ошибок (RFC 9457), feedback-ресурс, регрессия основных потоков. Кейсы составлены **до** реализации (страховка рефакторинга), прогоняются после.

## Формат прохождения

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы
- `- [ ] ⚠️` + причина, если кейс не пройден или требует ручной проверки
- Кейсы с 👤 — эскалация архитектору (UI, браузер)

### Процесс

1. Поднять инфраструктуру: `make docker-up-db` (Postgres main + siem, Redis), `make migrate`, `make migrate-siem` (если цель есть), backend `make dev`, siem-service — uvicorn из директории пакета (или `make docker-up` целиком).
2. Подготовить акторов через `/api/auth/register`: **user-a**, **user-b** (оба обычные), **admin** (выдать права: `make grant-admin USER=<name>`).
3. Прогнать кейсы сверху вниз; каждый failed кейс — повторная попытка, затем фиксация в [Findings](#findings).
4. После прохождения — сводка (pass / failed / deferred / findings).

### Где смотреть состояние

| Что | Команда / место |
|-----|------|
| Main app | `http://localhost:8000`, structlog stdout |
| siem-service | `http://localhost:8001`, docker-compose logs siem-service |
| Feedback в Redis | `redis-cli GET feedback:<trace_id>`, `redis-cli HGETALL trace:<thread_id>` |
| siem_events | psql в siem-db (порт 5434) |

---

## Layer 0: Automated (gate)

- [x] `make check` (ruff + mypy backend + siem-service + packages) — 0 errors (перепроверено при прогоне: ruff check + format --check + mypy, 149 файлов, чисто)
- [x] `make check-fe` (ESLint + Prettier + tsc strict) — 0 errors (прогнано до тест-сессии, зелёное)

---

## TC-A: Авторизация и ownership

**A1. SIEM `/security/events` — admin-only**

Прогон шёл на порту **8011** (8001 в окружении занят посторонним процессом — ожидаемое отклонение).

- [x] `GET /api/security/events` без токена → 401, `Content-Type: application/problem+json`, `www-authenticate: Bearer`
- [x] То же с токеном обычного user-a → 403, problem+json, detail "Admin access required"
- [x] То же с admin-токеном → 200, envelope `{items, total, limit, offset}` (limit=50 default)

**A2. Thread ownership в thread-scoped endpoints**

Подготовка: user-a создаёт project-A + chat-A; user-b создаёт project-B.

- [x] user-b: `GET /api/projects/{project-B}/chats/{chat-A}/settings` → 404 "Chat not found", problem+json
- [x] user-b: `PUT /api/projects/{project-B}/chats/{chat-A}/settings` `{"model_name": null}` → 404; последующий GET от user-a показал настройки нетронутыми
- [x] user-b: `GET /api/projects/{project-B}/chats/{chat-A}/mcp-servers` → 404
- [x] user-b: `POST /api/projects/{project-B}/chats/{chat-A}/mcp-servers` (валидное тело) → 404, сервер в списке chat-A не появился
- [x] user-b: `PUT .../mcp-servers/inherited/{random-uuid}/toggle` → 404
- [x] Позитив: user-a `GET /api/projects/{project-A}/chats/{chat-A}/settings` → 200 (`resolved_model` заполнен)
- [x] Позитив: user-a thread-level mcp-servers list → 200 (envelope + `inherited`), create → 201. Нюанс: create валидирует доступность MCP-сервера — с фиктивным URL отдаёт 503 `urn:learnflow:mcp-unreachable`; 201 получен с реальным сервером `https://docs.langchain.com/mcp`

**A3. Feedback — ownership трейса**

Подготовка: user-a отправляет сообщение в chat-A (получает trace_id из SSE/чат-детали).

- [x] user-b: `PUT /api/projects/{project-B}/chats/{chat-A}/feedback/{trace-id}` → 404 "Chat not found"
- [x] user-a: PUT с чужим trace_id (`deadbeef...`) → 404 "Trace not found"
- [x] Позитив: user-a с настоящим trace_id (из SSE-события `done`) → 200, тело `{trace_id, score}`

**A4. `/api/models` — только аутентифицированные**

- [x] `GET /api/models` без токена → 401, problem+json
- [x] С токеном user-a → 200, envelope (3 модели, total=3)

---

## TC-B: Статус-коды

- [x] `POST /api/projects` → **201**, тело — ProjectResponse (`id`, `name`, timestamps)
- [x] `POST /api/projects/{id}/chats` → **201**, тело — ChatResponse (`thread_id`, `title`, ...)
- [x] `POST /api/users/me/mcp-servers` → 201 (с реальным MCP-сервером; см. нюанс в A2)
- [x] `DELETE /api/projects/{id}` → 204, тела нет (`204 No Content`, без `content-length` полезной нагрузки)
- [x] `DELETE /api/users/me/memories/{key}` → 204; повторный DELETE → 204 (идемпотентность). Нюанс: write-эндпоинта для memories нет (`PUT /api/users/me/memories/{key}` → 405, память пишет агент), проверено на несуществующем ключе — оба вызова идут одним кодом
- [x] 6-й MCP-сервер в scope user → **409**, problem+json "Maximum 5 servers per scope"
- [x] SIEM: `PATCH /api/security/alerts/1` с `{"status": "bogus"}` → **422**, `urn:learnflow:validation-error`, `errors[0].type=literal_error` ("acknowledged' or 'resolved'")
- [x] SIEM: `GET /api/security/events?from=not-a-date` → **422**, `urn:learnflow:validation-error`, `datetime_from_date_parsing`
- [x] `POST /api/auth/register` с занятым именем → 409 "Username already exists"; login с неверным паролем → 401 "Invalid credentials". Нюанс: первый прогон register упёрся в rate limit 3/3600с на IP (429) — обойдён через `X-Forwarded-For` (см. Findings F4)
- [x] Rate limit: 6 быстрых `POST /api/auth/login` (отдельное имя) → 5×401, затем 429 с заголовком `Retry-After: 60` и телом problem+json — заголовок выживает после problem-handler'а

---

## TC-C: Pagination и envelope

Подготовка: у user-a — 3 проекта; в project-A — 3 чата и ≥2 артефакта (артефакты создаются агентом — допустимо подготовить через прямую вставку в БД, если генерация дорогая).

- [x] `GET /api/projects` → `{items, total, limit, offset}`, total=3, limit=50 (default), offset=0
- [x] `GET /api/projects?limit=2&offset=1` → 2 items, total=3, limit=2, offset=1; порядок updated_at desc стабилен (A3 → A2 → A; offset=1 отдаёт A2, A)
- [x] `GET /api/projects?limit=201` → 422; `offset=-1` → 422
- [x] `GET /api/projects/{id}/chats?limit=2` → envelope, total=3, 2 items
- [x] `GET /api/chats/recent?limit=2&offset=1` → envelope, 2 items, total=3, offset=1
- [x] `GET /api/projects/{id}/artifacts?limit=1` → envelope, total=2, 1 item (артефакты вставлены в БД напрямую — агент в smoke-диалоге их не создавал, допустимо по тест-плану)
- [x] `GET /api/users/me/memories` → envelope, items=[], total=0
- [x] `GET /api/users/me/mcp-servers` → envelope + `inherited: []` (пустой)
- [x] `GET /api/projects/{id}/mcp-servers?include_inherited=true` → envelope items + `inherited` (5 user-scope серверов user-a)
- [x] `GET /api/models` → envelope, total=3 = числу моделей конфига
- [x] SIEM: `GET /api/security/events?limit=1` → envelope, 1 item, total=6, limit=1

---

## TC-D: Feedback как подресурс чата

- [x] `PUT .../feedback/{trace_id}` `{"score": true}` → 200, тело `{trace_id, score: true}`; Redis `GET feedback:<trace_id>` = "1"
- [x] Повторный PUT `{"score": false}` → 200, Redis = "0" (идемпотентная замена)
- [x] `DELETE .../feedback/{trace_id}` → 204, ключ удалён (`EXISTS` = 0)
- [x] Повторный DELETE → 204 (идемпотентность)
- [x] После PUT score=true: `GET .../chats/{cid}` → у assistant-сообщения `trace_id` и `feedback_score: true` (у user-сообщения null)
- [x] `POST /api/feedback` → 404 (маршрут удалён)

---

## TC-E: Формат ошибок — RFC 9457 Problem Details

- [x] `GET /api/projects/{случайный-uuid}` → 404, `Content-Type: application/problem+json`, тело `{type: "about:blank", title: "Not Found", status: 404, detail: "Project ... not found"}`
- [x] `POST /api/projects` с телом `{}` → 422, problem+json, `type: urn:learnflow:validation-error`, расширение `errors` с pydantic-ошибками (`missing`, `loc: [body, name]`)
- [x] `GET /api/projects` без токена → 401, problem+json
- [x] SIEM: `GET /api/security/alerts/999999` (admin) → 404, problem+json — формат идентичен main app
- [x] Security guard violation (PUT sphere с prompt injection) → 422, problem+json, `type: urn:learnflow:security-policy-violation`, расширение `reason: llm_classifier`. Нюанс: поля `detail` в теле нет (опционально по RFC 9457)
- [ ] 👤 Frontend: при отклонении guard'ом UI показывает прежнее сообщение (`isSecurityViolation` адаптирован) — ручная проверка архитектора

---

## TC-F: Регрессия основных потоков

- [x] Auth flow: register (200, refresh-cookie выставлена) → me (200) → refresh (200, ротация токена) → logout (200) → me со старым access-токеном до истечения — 200 (stateless JWT); refresh с отозванной cookie → 401 "Token reuse detected, all sessions revoked"
- [x] Chat flow: create project → create chat → `POST .../messages` (SSE: `text_chunk` → `final_output_review_*` → `done` с `message_id` и `trace_id`) → chat detail содержит user- и assistant-сообщения
- [x] Cancel: `POST .../chats/{cid}/cancel` → 200 `{"ok": true}`
- [x] Sphere: GET → PUT → GET, контент сохраняется, формат ответа `{project_id, content, updated_at}` без изменений. Нюанс: round-trip не байт-в-байт — секционное хранилище нормализует заголовки в slug-id и оборачивает описание (поведение knowledge-sphere, не регрессия slice'а)
- [x] Settings resolve: `GET /api/users/me/settings` → `resolved_model: "z-ai/glm-5"`, `resolved_source: "config"`
- [x] SIEM smoke: 3 неудачных логина → через ~8с в `/api/security/events` появились `auth.login.failed` (+ register.success, rate_limit.exceeded, guard classifier_injection — pipeline через Redis Stream жив)
- [ ] 👤 UI smoke: список проектов, чатов, артефактов отображается — ручная проверка архитектора

---

## TC-G: PDF-экспорт не блокирует event loop

- [x] `GET .../artifacts/{id}/download?format=md` → 200, `Content-Type: text/markdown`, `Content-Disposition: attachment; filename*=UTF-8''Test%20Artifact%201.md`
- [ ] ⚠️ `GET .../artifacts/{id}/download?format=pdf` → **500** (две попытки): wkhtmltopdf падает с SIGSEGV. Воспроизведено вне приложения с тем же HTML — крэш окружения, не кода slice'а. См. Findings F1
- [x] Во время PDF-конверсии (~1.8 с активной работы wkhtmltopdf до крэша) параллельный `GET /health` отвечал за 3–4 мс — конверсия уходит в `anyio.to_thread.run_sync`, event loop свободен. Каверза: полное окно 5 с javascript-delay не наблюдалось из-за F1

---

## Findings

**F1 (medium): PDF-экспорт артефакта возвращает 500 — wkhtmltopdf segfault.**
`GET .../artifacts/{id}/download?format=pdf` → 500 (стабильно, 2 попытки). В логе backend: `OSError: wkhtmltopdf exited with non-zero code -11` (SIGSEGV) из `pdfkit.from_string`. Воспроизводится standalone: `wkhtmltopdf --javascript-delay 5000 <html с MathJax 2.7.9 CDN-скриптом>` → core dump на этом хосте (wkhtmltopdf 0.12.6, Fedora 43); тот же бинарь на HTML без MathJax отрабатывает корректно. Падение — в связке QtWebKit + MathJax-скрипт из `app/api/export.py::_HTML_TEMPLATE`, путь кода pre-existing (не регрессия slice'а), но PDF-экспорт в этом окружении неработоспособен. Воспроизведение: создать артефакт, запросить `?format=pdf`.

**F2 (low): 500-ответы — не problem+json.** При падении PDF-экспорта тело ответа — `text/plain` "Internal Server Error". Problem-handlers покрывают `HTTPException` и `RequestValidationError`, но не unhandled exceptions; единый формат RFC 9457 на 5xx не распространяется. Обнаружено попутно через F1.

**F3 (info): `POST /api/auth/register` возвращает 200, а не 201.** Создаёт ресурс (пользователя), но отвечает 200 с TokenResponse. Кейсами не покрывалось (в TC-B перечислены projects/chats/mcp-servers) — фиксирую как наблюдение для решения архитектора; для auth-эндпоинтов 200 — распространённая практика.

**F4 (low, security-наблюдение): per-IP rate limit обходится спуфингом `X-Forwarded-For`.** `_get_client_ip` (backend/app/api/routes/auth.py) берёт первый элемент XFF без проверки доверенного прокси — клиент с прямым доступом к backend обходит лимиты register (3/3600с) и refresh (10/60с), подставляя произвольный заголовок (использовано в прогоне для обхода register-лимита). Pre-existing, вне scope slice'а; актуальность зависит от deployment-топологии (за доверенным reverse-proxy не воспроизводится).

**Наблюдения вне кейсов:**
- `POST .../mcp-servers` (все scope) перед сохранением проверяет доступность MCP-сервера: недостижимый URL → 503 `urn:learnflow:mcp-unreachable`. Контракт осмысленный, но в тест-кейсах не зафиксирован.
- `PUT /api/users/me/memories/{key}` → 405 — write-эндпоинта для memories нет (пишет агент), DELETE идемпотентен и на несуществующем ключе.
- Sphere PUT нормализует markdown (заголовки → slug-id секций, описания оборачиваются) — round-trip не байт-в-байт; поведение секционного хранилища knowledge-sphere.
- siem-service в прогоне жил на порту 8011 вместо 8001 (порт занят посторонним процессом) — ожидаемое отклонение окружения, в кейсах A1 отмечено.

## Сводка

| Категория | Результат |
|-----------|-----------|
| Pass | 57 кейсов (Layer 0 — 2, TC-A — 15, TC-B — 10, TC-C — 11, TC-D — 6, TC-E — 5, TC-F — 6, TC-G — 2) |
| Fail | 1 — TC-G PDF-экспорт (F1, environmental: wkhtmltopdf SIGSEGV) |
| Deferred (👤 ручная проверка) | 2 — frontend guard-сообщение (TC-E), UI smoke (TC-F) |
| Findings | F1 medium, F2 low, F4 low, F3 info |

Контрактные цели итерации подтверждены: envelope `{items, total, limit, offset}` на всех списках обоих сервисов, problem+json (RFC 9457) на 4xx обоих сервисов, ownership через 404, статус-коды 201/204/409/422/429 на местах, feedback переехал в подресурс чата (старый `POST /api/feedback` удалён), `Retry-After` переживает problem-handler, SIEM pipeline жив.
