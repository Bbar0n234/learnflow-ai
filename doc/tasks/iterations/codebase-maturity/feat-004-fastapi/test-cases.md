# Тест-кейсы: feat-004 Backend / FastAPI Slice + SIEM Hygiene

Ручные тест-кейсы на участки, затронутые рефакторингом. Прогоняются независимым
агентом-тестировщиком на поднятом стенде после внесения правок. Точечные
автотесты (помечены `[auto]`) дублируют критичные пути и живут в `backend/tests/`.

## Что меняется (зона риска)

- Main app: `Settings` в `app.state` (deps, auth-роуты, feedback), `RateLimiter`
  в `app.state`, argon2 через `anyio.to_thread`, CSV-парсинг `CORS_ORIGINS`,
  Annotated-стиль (artifacts, chats, auth cookies), блокирующие вызовы в feedback.
- SIEM: `MetaEmitter` без синглтона (lifespan → `app.state` → Depends), импорт
  `SecurityEvent` из `siem_contracts`, `infra/db.py` без глобалей, `CorrelationEngine`
  без фабрики-синглтона, `main.py` через `create_app()` + Settings (включая
  `SIEM_FRONTEND_ORIGIN`), `jwt_secret` обязателен, убран дубль health,
  Annotated-стиль в routes.
- Сквозное: StrEnum-миграция security-энумов, bump uv в Dockerfile'ах.

## Стенд

```bash
docker compose up -d --build        # полный стек: app:8000, siem-service:8001
make migrate && make migrate-siem   # миграции (если чистые БД)
```

Для admin-кейсов SIEM нужен пользователь с `is_admin`: `make grant-admin USER=<name>`
(после регистрации), затем перелогин — свежий access token несёт `is_admin=true`.

---

## 1. Boot & health

| # | Шаги | Ожидаемо |
|---|------|----------|
| 1.1 | `docker compose up -d --build` — оба образа собираются | Сборка зелёная (uv bump не сломал) |
| 1.2 | `curl -f localhost:8000/health` | `{"status":"ok"}`, 200 |
| 1.3 | `curl -f localhost:8001/health` | `{"status":"ok"}`, 200 |
| 1.4 | `curl -s -o /dev/null -w '%{http_code}' localhost:8001/api/security/health` | **404** — дубль health удалён |
| 1.5 | Логи app: `docker compose logs app` | `app started`, `security guard initialized`, `security event publisher started`, без traceback |
| 1.6 | Логи siem: `docker compose logs siem-service` | `subscriber task started`, `correlation engine task started`, без traceback |
| 1.7 | `docker compose stop siem-service && docker compose logs siem-service --tail 20` | Graceful shutdown: cancel задач, `redis closed`, `database closed`, без ошибок |

## 2. Auth — критичный путь `[auto]`

Все запросы к `localhost:8000/api/auth/*`.

| # | Шаги | Ожидаемо |
|---|------|----------|
| 2.1 | `POST /register` `{"name":"t1","password":"secret123"}` | 200, `access_token`; Set-Cookie `refresh_token` (HttpOnly, Path=/api/auth, SameSite=lax) |
| 2.2 | Повторный `POST /register` с тем же именем | 409 `Username already exists` |
| 2.3 | `POST /login` верные креды | 200, `access_token`, новый refresh cookie |
| 2.4 | `POST /login` неверный пароль | 401 `Invalid credentials` |
| 2.5 | `GET /me` с Bearer из 2.3 | 200, `{id, name, is_admin:false}` |
| 2.6 | `GET /me` без токена / с мусорным токеном | 401 |
| 2.7 | `POST /refresh` с cookie из 2.3 | 200, новый access + новый refresh cookie |
| 2.8 | Повторный `POST /refresh` со **старым** cookie (replay) | 401 `Token reuse detected...`; cookie удалён |
| 2.9 | `POST /logout` с действующим cookie, затем `POST /refresh` с ним же | logout 200; refresh 401 |
| 2.10 | Rate limit: 6× `POST /login` c неверным паролем подряд (лимит 5/60с) | 6-й ответ 429 + header `Retry-After` |
| 2.11 | Латентность: время ответа `POST /login` (argon2 в threadpool) | Сопоставимо с до-рефакторинга (~сотни мс), event loop не виснет: параллельный `GET /health` во время серии логинов отвечает мгновенно |

`[auto]`: hash/verify roundtrip через `anyio.to_thread`, отказ verify на чужом
пароле, rate limiter (окно/лимит/retry_after) — `backend/tests/`.

## 3. CORS main app (CSV-парсинг) `[auto]`

| # | Шаги | Ожидаемо |
|---|------|----------|
| 3.1 | Preflight: `curl -X OPTIONS localhost:8000/api/auth/login -H 'Origin: http://localhost:5173' -H 'Access-Control-Request-Method: POST'` | 200, `access-control-allow-origin: http://localhost:5173` |
| 3.2 | То же с `Origin: http://evil.example` | Ответ **без** `access-control-allow-origin` |
| 3.3 | Запуск с `CORS_ORIGINS=http://a.test,http://b.test` в env | Preflight с `Origin: http://b.test` проходит; дефолтный 5173 — нет |

`[auto]`: unit на validator — CSV-строка, строка с пробелами, list passthrough.

## 4. Feedback (блокирующие вызовы)

Предусловие: Langfuse настроен (ключи в env). Если нет: create-путь (4.1) даёт
200 — disabled-клиент SDK v3 молча no-op'ит `create_score/flush`; delete-путь
(4.2) идёт прямым REST и даёт 503. Зафиксировано прогоном 2026-06-12.

| # | Шаги | Ожидаемо |
|---|------|----------|
| 4.1 | Отправить сообщение в чат (UI или API), получить `trace_id`; `POST /api/feedback` `{"trace_id":..., "score":true}` с Bearer | 200 `{"status":"success"}` (и при ненастроенном Langfuse — no-op SDK) |
| 4.2 | `POST /api/feedback` `{"trace_id":..., "score":null}` (снятие оценки) | 200; повторное снятие — тоже 200 (идемпотентность 404→pass) |
| 4.3 | Во время 4.1-4.2 параллельный `GET /health` | Отвечает мгновенно (httpx/langfuse не блокируют loop) |

## 5. Artifacts download

Предусловие: в проекте есть артефакт (создать через чат-поток или напрямую в БД).

| # | Шаги | Ожидаемо |
|---|------|----------|
| 5.1 | `GET /api/projects/{pid}/artifacts/{aid}/download?format=md` | 200, `text/markdown`, Content-Disposition attachment |
| 5.2 | `GET ...?format=pdf` | 200, `application/pdf` (wkhtmltopdf в образе) |
| 5.3 | `GET ...?format=exe` | 422 (валидация Query pattern сохранилась после Annotated) |

## 6. Chat SSE smoke

| # | Шаги | Ожидаемо |
|---|------|----------|
| 6.1 | Создать проект и чат, `POST /api/.../messages` — поток SSE | События идут, поток завершается; в логах нет ошибок enum-сериализации (StrEnum) |
| 6.2 | В Redis: `XRANGE security.events - + COUNT 20` после чата | События guard'а имеют `event_type` вида `agent.guard.input.*` (значения не изменились после StrEnum) |

## 7. SIEM API — admin RBAC и пагинация

Все запросы к `localhost:8001/api/security/*`. `$ADMIN` — Bearer админа (см. Стенд),
`$USER` — токен обычного пользователя.

Примечание: на этой ветке `GET /events` ещё без `require_admin` — RBAC на events
добавляет feat-002 (cm/feat-002-rest-api); закрытие P1 из backlog произойдёт при merge.

| # | Шаги | Ожидаемо |
|---|------|----------|
| 7.1 | `GET /alerts` без токена | 401/403 (HTTPBearer) |
| 7.2 | `GET /alerts` c `$USER` | 403 `Admin access required` |
| 7.3 | `GET /events?limit=5` | 200, envelope `{items,total,limit,offset}`; в items видны auth-события из кейса 2 (pipeline жив) |
| 7.4 | `GET /events?severity=warning` | 200, все items с `severity=warning` |
| 7.5 | `GET /alerts`, `GET /rules` c `$ADMIN` | 200, envelope |
| 7.6 | `GET /rules/999999` | 404 |

## 8. SIEM meta-события (MetaEmitter через app.state) `[auto]`

Критичный путь SIEM pipeline: admin-действие → XADD `security.events` → subscriber
→ строка в `siem_events`.

| # | Шаги | Ожидаемо |
|---|------|----------|
| 8.1 | `POST /rules` c `$ADMIN`: `{"name":"tc-rule","rule_type":"threshold","config":{"event_type_pattern":"auth.login.failed","threshold":3,"window_seconds":300,"group_key":"ip"},"severity":"warning"}` (схема config — как у seed-правил; движок молча пропускает правила с незнакомой схемой: `threshold_rule_missing_pattern` в логах) | 201, тело правила |
| 8.2 | Redis: `XRANGE security.events - + COUNT 50` | Есть событие `siem.rule.created` с `identifiers.user_id` = id админа; JSON соответствует контракту `siem_contracts` (`event_id` UUID, `timestamp` ISO) |
| 8.3 | Через ~5с: `GET /events?event_type=siem.rule.created` | Событие в `siem_events` (loopback consumer отработал) |
| 8.4 | `PATCH /rules/{id}` `{"enabled":false}` → `DELETE /rules/{id}` | 200 → 204; в стриме `siem.rule.updated`, `siem.rule.deleted` |
| 8.5 | При наличии алерта (см. 9): `PATCH /alerts/{id}` `{"status":"acknowledged"}` затем `{"status":"resolved"}` | 200 оба; meta-события `siem.alert.acknowledged/resolved` в стриме |
| 8.6 | `PATCH /alerts/{id}` `{"status":"bogus"}` | 400 (ручная валидация в handler на этой ветке; 422 схемой — после merge feat-002, который переносит её в `AlertPatchRequest`) |

`[auto]`: `MetaEmitter.emit()` сериализует контрактный `SecurityEvent`
(`event_id`/`timestamp` генерируются, `event_type` из vocabulary) — unit с fake redis.

## 9. SIEM correlation engine (без синглтона)

| # | Шаги | Ожидаемо |
|---|------|----------|
| 9.1 | Создать threshold-правило из 8.1 (enabled), затем 3+× неверный логин (кейс 2.4) в течение окна | Через ≤2 poll-цикла (`SIEM_POLL_INTERVAL_SECONDS`, дефолт 10с) появляется алерт: `GET /alerts` → item со `status=new`, `rule_id` правила |
| 9.2 | Логи siem-service за период | `alert_processed` есть; `correlation_engine_error` отсутствует |

## 10. SIEM CORS из Settings

| # | Шаги | Ожидаемо |
|---|------|----------|
| 10.1 | Preflight `OPTIONS localhost:8001/api/security/events` c `Origin: http://localhost:5173` | `access-control-allow-origin` присутствует |
| 10.2 | То же с посторонним Origin | Заголовка нет |

## 11. SIEM jwt_secret обязателен

| # | Шаги | Ожидаемо |
|---|------|----------|
| 11.1 | Запуск siem-service без `SIEM_JWT_SECRET` в env (локально: `cd services/siem-service && uv run python -c "from siem_service.config import Settings; Settings()"` при очищенном env) | ValidationError — сервис не стартует с пустым секретом |

## 12. StrEnum-регрессия `[auto]`

| # | Шаги | Ожидаемо |
|---|------|----------|
| 12.1 | `uv run python -c "from app.agent.security.types import Checkpoint, Verdict; assert Checkpoint.USER_INPUT.value == 'user_input'; assert Verdict.INJECTION.value == 'INJECTION'"` (из backend/) | Без исключений; `.value` не изменились |
| 12.2 | Кейс 6.2 (значения event_type в стриме) | Значения идентичны до-рефакторинговым |

`[auto]`: asserts на `.value` всех четырёх энумов + сериализация `GuardResult.model_dump()`.

---

## Чек-лист прогона

- [ ] 1.1–1.7 Boot & health
- [ ] 2.1–2.11 Auth + rate limit
- [ ] 3.1–3.3 CORS main app
- [ ] 4.1–4.3 Feedback (или зафиксирован skip: langfuse не настроен)
- [ ] 5.1–5.3 Artifacts
- [ ] 6.1–6.2 Chat SSE + guard events
- [ ] 7.1–7.6 SIEM RBAC
- [ ] 8.1–8.6 SIEM meta-события
- [ ] 9.1–9.2 Correlation
- [ ] 10.1–10.2 SIEM CORS
- [ ] 11.1 jwt_secret
- [ ] 12.1–12.2 StrEnum
