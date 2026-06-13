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

Все отложенные по решению архитектора пункты зафиксированы в `doc/backlog.md` (§ Backend и § Security), чтобы ничего не пропадало молча:

- **Feedback resource modeling** (backlog § Backend, P3): убрать протечку `trace_id` в контракт, перейти на доменную адресацию по `message_id`. Текущий вложенный вариант B принят осознанно (ownership-безопасен, консистентен с API); рефакторинг — на вырост, требует проработки маппинга message↔trace.
- **5xx не в problem+json** (backlog § Backend, P3 → feat-007): форма ответа на 500; философия обработки — в feat-007.
- **Дубль `problem.py`** (backlog § Backend, P3 → feat-004): вынос в shared решается вместе с консолидацией `SecurityEvent`.
- **PDF-экспорт** (backlog § Backend, P2): wkhtmltopdf deprecated + segfault на MathJax; замена с поддержкой математики.
- **MCP `mcp_unreachable` 503-семантика** (backlog § Backend, P3): код неточен (правильнее 422/502), security fail-closed корректен.
- **`X-Forwarded-For` спуфинг** (backlog § Security, P2): обход per-IP rate limits; зависит от топологии прода.
- **UI-пагинация frontend** — контракт готов, frontend берёт `limit=200`; постраничная подгрузка — задача frontend slice (feat-006).
- Класс ошибок группы A (auth/ownership) механически покрывается тестами «каждый endpoint с авторизацией → кейсы 401/403/чужой ресурс» — вход для test philosophy feat-009.

Закрытый дубль: дыра A1 (SIEM `/events` без `require_admin`) была заведена в backlog как P1 (Security) — закрыта этим slice'ем, пункт удалён тем же PR.
