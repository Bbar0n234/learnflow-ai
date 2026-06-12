# Summary: feat-002 — REST API Slice

## Что сделано

Аудит всех REST endpoints (main app ~50 + siem-service) против skill `api-design-principles` + общие паттерны чистого кода; точечные правки по согласованным с архитектором решениям; контрактные тест-кейсы составлены до правок и прогнаны после ([test-cases.md](test-cases.md): 57 pass / 1 fail / 2 deferred 👤).

### Закрытые findings

**Безопасность и корректность (найдено сверх бэклога):**
- `GET /api/security/events` был без авторизации (документация заявляла admin-only) — добавлен `require_admin`.
- Thread ownership не проверялся в thread-scoped endpoints (settings, все 6 thread-level mcp-servers) — IDOR через подстановку чужого `thread_id`. Введён общий dependency `UserThread` (по образцу `UserProject`), применён везде, включая messages/chats (заменил ручные проверки).
- Feedback не проверял принадлежность `trace_id` — закрыто редизайном ресурса (см. ниже).
- `GET /api/models` был единственным неаутентифицированным endpoint — добавлен `CurrentUser`.

**Пункты аудита 2026-04-04 (бэклог):** полный список из 8 пунктов не был сохранён в документации; закрыты 4 зафиксированных + всё найденное повторным аудитом:
- Pagination offset/limit на всех list endpoints (решение «пагинация везде», включая малые списки): `limit` default 50 / max 200, `offset` ≥ 0, общий dependency `Pagination`.
- Единый envelope `{items, total, limit, offset}` — generic `Page[T]` (`app/api/schemas/common.py`).
- `201` на POST create (projects, chats); `409` вместо `400` на лимит MCP-серверов.
- Feedback переделан с `POST /feedback {trace_id, score|null}` (тройная семантика) на подресурс чата: `PUT | DELETE /projects/{id}/chats/{cid}/feedback/{trace_id}`.

**Формат ошибок:** RFC 9457 Problem Details (`application/problem+json`) на обоих сервисах — глобальные handlers (`app/api/problem.py`, зеркало в `siem_service/api/problem.py`), машинные коды `urn:learnflow:<code>`, стихийный полиморфный `detail` ликвидирован. Frontend: `security-error.ts` переведён на `type`-проверку; `AuthGate` не потребовал правок (`detail` сохранился как human-readable поле).

**Россыпь:** `Literal` в `AlertPatchRequest` (422 вместо ручной 400), `exclude_unset` в rule update (можно занулить description), `response_model` на toggle endpoints, `datetime`-параметры в SIEM events (422 на битую дату), унификация path-параметра `{chat_id}` (вместо смеси с `{thread_id}`), pdfkit уведён из event loop (`anyio.to_thread.run_sync`).

### Конвенции

`doc/tech/conventions.md` § REST API: pagination/envelope, status code policy (+ auth-RPC исключение), RFC 9457, ownership-зависимости, граница нейминга chat/thread (path — chat, payload/domain — thread), отказ от версионирования до публичного API. Обновлены `backend.md` (Schemas, PDF-drift pandoc→pdfkit), `observability.md` (feedback-контракт), `siem-service.md` (error format).

## Отклонения от согласованного

- **Feedback URL**: согласовывался `PUT/DELETE /traces/{trace_id}/feedback`; реализован `PUT/DELETE /projects/{id}/chats/{cid}/feedback/{trace_id}`. Причина: обратного маппинга trace→владелец в системе нет (TraceStore хранит `thread → {message: trace}`), плоский URL потребовал бы новую Redis-схему + не работал бы для существующих данных. Вложенный вариант валидирует ownership существующей цепочкой. Семантика (идемпотентные PUT/DELETE) — как согласовано.
- **Тестовый прогон SIEM шёл на порту 8011** — порт 8001 занят посторонним процессом (graphrag MCP-server другого проекта). Код/конфигурация не менялись.

## Follow-ups (вне scope slice'а)

- **UI-пагинация frontend** — контракт готов, frontend пока берёт `limit=200` одним запросом; постраничная подгрузка — задача frontend slice (feat-006) или отдельная. Зафиксировано по решению архитектора.
- **PDF-экспорт неработоспособен в dev-окружении** (Findings F1): wkhtmltopdf 0.12.6 на Fedora 43 сегфолтится на MathJax-скрипте; воспроизводится вне приложения. Путь pre-existing; кандидат на замену стека конвертации (weasyprint/playwright print) — feat-004 или backlog.
- **5xx не в problem+json** (F2): unhandled exceptions отдаются как `text/plain` от ServerErrorMiddleware; распространение RFC 9457 на 500 — решение к feat-007 (error handling philosophy).
- **`X-Forwarded-For` спуфинг** (F4): `_get_client_ip` доверяет заголовку без проверки прокси → обход per-IP rate limits. Pre-existing, кандидат в backlog (security).
- Класс ошибок группы A (auth/ownership) механически покрывается тестами «каждый endpoint с авторизацией получает кейсы 401/403/чужой ресурс» — вход для test philosophy feat-009.
