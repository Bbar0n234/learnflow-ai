# Summary: feat-002 — REST API Slice

## Контекст

Slice фазы **Codebase Maturity Pass** ([tasklist](../../../tasklist-codebase-maturity.md)) — «взросление» кодовой базы: единые паттерны, конвенции и тесты по слоям через аудит каждого домена в паре с релевантным skill'ом. Этот slice — домен **REST / backend**: применить skill `api-design-principles` ко всем REST endpoints обоих сервисов (main app + siem-service) и закрыть REST API cleanup из бэклога (аудит 2026-04-04: pagination, status codes, envelope, DELETE feedback через POST). Границы — scope + DoD итерации feat-002.

**Как шла работа:** автономный аудит endpoints против skill + общие паттерны чистого кода → findings архитектору на разбор (два раунда) → согласование решений по развилкам → точечная реализация только после апрува → контрактные тест-кейсы (составлены до правок, прогнаны после отдельным сабагентом-tester на живом стеке) → конвенции в `conventions.md` → push + PR в develop (merge за архитектором). Развилки на «точках остановки на теорию» (RFC 9457 vs custom, offset/limit vs cursor, resource modeling) разбирались с архитектором до выбора.

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

## Развилки и принятые решения

Журнал архитектурных выборов slice'а — что рассматривали, что выбрали, почему. Решения принимал архитектор; здесь зафиксированы обоснования.

1. **Формат ошибок: RFC 9457 vs упорядоченный `{detail}`.** Триггер — стихийно заведшийся полиморфный `detail` (обычно строка, но в трёх сервисах — объект `{error: code}`), фронт уже завязался на это в `security-error.ts`. Рассматривали: (A) оставить `{detail}`, узаконив объектную форму для машинных кодов — нулевая миграция, но консервирует полиморфизм и нестандарт; (B) RFC 9457 Problem Details — стандарт IETF, единая форма, машинный код в `type`. **Выбрали B.** Обоснование: цена низкая (две точки на фронте, два handler'а на бэк), а вариант A консервирует костыль, который уже дал протечку. Единый формат на оба сервиса.

2. **Pagination: offset/limit vs cursor.** **Выбрали offset/limit.** Коллекции — десятки-сотни элементов на пользователя; cursor (стабильность при дописывании, большие датасеты) — overkill для таких объёмов.

3. **Envelope — где применять.** Рассматривали: пагинировать только растущие коллекции (малые списки — models, mcp-servers — оставить голым `{items}`) vs пагинировать всё. **Выбрали «везде», включая малые фиксированные списки.** Обоснование архитектора: единообразие важнее экономии полей — не держать в голове «этот список может вырасти, а этот нет»; шум `total: 3, limit: 50` дешевле, чем ветвление в клиенте. Канон — `{items, total, limit, offset}`, generic `Page[T]`.

4. **Feedback — модель ресурса.** Три варианта URL: (A) плоский `/traces/{trace_id}/feedback` — REST-чистейший, но нет обратного маппинга trace→владелец, потребовал бы новый Redis-индекс и не работал бы для существующих данных; (B) вложенный `/projects/{id}/chats/{cid}/feedback/{trace_id}` — ownership бесплатно по существующей цепочке, но depth-3 и протечка Langfuse-`trace_id` в контракт; (C) доменный `.../messages/{message_id}/feedback` — чистейший доменно (без протечки trace_id), но требует работы с маппингом message↔trace. **Выбрали B сейчас**, A отклонён (инфраструктурное вложение ради косметики), **C заведён в backlog** как целевой рефакторинг на вырост. Старый `POST /feedback {trace_id, score|null}` с тройной семантикой (create/update/delete в одном POST) заменён идемпотентными `PUT`/`DELETE`.

5. **Нейминг chat vs thread.** URL-сегмент везде `chats`, но path-параметр звался то `chat_id`, то `thread_id`; поля payload и domain — `thread_id` (идёт из LangGraph). Варианты: (O1) унифицировать только path-параметры до `chat_id`, поля не трогать — ноль правок фронта; (O2) переименовать и поля ответов в `chat_id` — дорого, чисто косметика; (O3) всё на `/threads` — ломает фронт. **Выбрали O1.** Граница зафиксирована в conventions: URL и path-параметры — `chat` (user-facing), payload и внутренние слои — `thread` (domain).

6. **Status codes.** `201` на POST create, `204` на DELETE (идемпотентно), `409` на конфликт лимита (вместо `400`), `422` через схему (`Literal`, `datetime`) вместо ручных `if`+`400`. **Auth-эндпоинты — осознанное исключение:** `POST /auth/register` оставлен на `200` (RPC-семантика — ответ это токен-сессия, не представление ресурса); `Location`-header на 201 решили не вводить (внутренний API, фронт не использует) и в conventions это не фиксировать как мелочь.

7. **Versioning.** **Не версионируем** (`/api` без `v1`) до появления публичного API — зафиксировано в conventions.

8. **Scope группы A (ownership/authz-дыры).** Найдены сверх бэклога (IDOR в thread-scoped endpoints, `/security/events` без admin, feedback без проверки trace, `/models` без auth). Развилка: чинить в REST-slice или вынести. **Решили чинить здесь** — findings REST-смежные, откладывать дыры нелогично.

9. **Тесты — только ручные контрактные кейсы.** Рассматривали добавить точечные автотесты на группу A (auth-путь — критичный, фаза это допускает). **Решение архитектора: не добавлять**, остаёмся на ручных/контрактных кейсах, прогнанных tester-сабагентом; автотесты — системно в feat-009. Класс «каждый endpoint с авторизацией → кейсы 401/403/чужой ресурс» зафиксирован как вход для test philosophy feat-009.

10. **pdfkit в event loop.** Блокирующий вызов (~5s `javascript-delay`) уведён через `anyio.to_thread.run_sync` — не чинит сам PDF (см. follow-ups), но перестаёт морозить event loop для всех клиентов.

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
