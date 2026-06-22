# Ф3 · S5 — Chat & streaming · run-log

Скоуп S5: критпуть SSE на максимальную глубину. Тесты ходят через публичный
интерфейс (HTTP-роуты и `ChatService`); прод-код не правился. Замороженная инфра
(`packages/testing`, общий conftest) не трогалась — всё scope-local в
`backend/tests/chat/`.

## Файлы

- `backend/tests/chat/conftest.py` — scope-local фикстуры и фейки:
  `FakeAgentRunner` (программируемая последовательность событий, `raise_after` для
  in-stream краша), `FakeThreadViewRepo` / `FakeArtifactRepo` (spy на
  `set_message_id`) / `FakeTraceStore` (флаги деградации); фикстуры `fake_runner` и
  `wired_runner` (override `get_chat_service` на реальные репозитории +
  фейк-раннер, т.к. под `ASGITransport` lifespan не поднимается и
  `app.state.agent_runner` пуст).
- `backend/tests/chat/test_chat_service.py` — sociable-unit `ChatService` на
  фейках (15 тестов).
- `backend/tests/chat/test_chat_routes.py` — HTTP-интеграция CRUD чатов (7).
- `backend/tests/chat/test_message_stream.py` — SSE-эндпоинт целиком через async
  `client.stream()` (8).
- `backend/tests/chat/test_feedback.py` — HTTP-интеграция feedback, Langfuse как
  внешний эффект (mock), Redis — in-memory fake (7).

## Покрытые поведения

**ChatService (sociable-unit, фейки в памяти):**
- create/list — возврат `ThreadView`, total.
- `get_chat`: 404 на отсутствующем треде; сборка истории + `trace_ids` +
  `feedback_scores`; **graceful-деградация** при падении trace-store на чтении
  `get_by_thread` и отдельно на `get_feedback_batch` (история отдаётся, trace-данные
  молча пустые — Redis некритичен).
- `send_message` оркестрация: 404 defense-in-depth; **фильтрация `trace_id`**
  (потребляется внутри, на провод не уходит) + терминальный `done` с
  `message_id`/`trace_id`; **линковка artifact'ов** к message_id
  (`set_message_id`); **взаимоисключающие терминалы** `error`/`security_block` vs
  `done` (parametrized — при ошибке `done` НЕ эмитится); запись `trace_id` в store;
  свертывание сбоя post-hoc резолва message_id (стрим всё равно завершается `done`
  с пустым message_id); `touch` треда.
- `cancel` — проброс результата раннера (parametrized True/False).

**CRUD-роуты (HTTP, реальные репозитории на транзакционной сессии):**
- create 201 + дефолт title "New Chat" при пропуске; create в чужой проект → 404.
- list — пагинация (total/limit/items), get — история сообщений; get чужого треда
  → 404; `/chats/recent` — треды юзера с `project_name` через eager-load.

**SSE-эндпоинт (критпуть, async `.stream()`):**
- `text/event-stream`, маппинг событий в wire-формат, **порядок** и фильтрация
  `trace_id`, терминальный `done` с полным payload.
- `error`-событие терминально — `done` следом НЕ идёт.
- **исключение раннера в середине потока** (`raise_after`) → генератор
  `_event_generator` ловит и эмитит терминальный `{"type":"error","message":"Stream
  failed"}` вместо тихого обрыва.
- пустой `content` принимается на уровне контракта, поток нормально завершается.
- POST в security-blocked тред → 403 (`require_unblocked_thread`); POST в чужой тред
  → 404; cancel-роут → `{"ok": bool}` (parametrized).

**Feedback (HTTP, Langfuse = внешний эффект → mock):**
- `set_feedback` → `langfuse.create_score(...)` с точным payload (parametrized
  score True→1 / False→0, `data_type=BOOLEAN`, `score_id`); неизвестный trace → 404
  (Langfuse не дёргается); нет Redis → 503; Langfuse недоступен
  (`httpx.ConnectError`) → 503.
- `delete_feedback` → 204; идемпотентность — 404 от Langfuse на удалении не всплывает
  как ошибка (по-прежнему 204).

## Результат `make test-scope P=backend/tests/chat`

`37 passed in ~11s`. Lint/type точечно: `ruff check` + `ruff format --check` —
чисто; `mypy backend/` (канонический гейт с pydantic-плагином) — на файлах скоупа
ошибок нет.

## Баги для Ф5

- **`MessageCreate.content` без валидации** (`backend/app/api/schemas/messages.py`):
  поле `content: str` — нет `min_length`, нет strip. Пустая строка (и строка из
  пробелов) принимается и уходит в агента/граф как валидное сообщение. Эндпоинт
  отвечает 200 и стримит. Тест `test_stream_accepts_empty_content` фиксирует это как
  **текущее** поведение (не как желаемое) — если контракт должен отклонять пустой
  ввод (422), это правка схемы + разворот ассерта. Решение за архитектором/Ф5.

Прод-код под тест не правился; ложно-зелёных нет (mock только на Langfuse —
единственный внешний эффект, проверяется payload/факт вызова).

## Непокрытое и почему

- **Реальный `AgentRunner` (`app/agent/runner.py`)** — это граф/ноды (скоуп S3),
  вне S5. `backend/app/services/agent_runner.py` в моём скоупе — только `Protocol`
  + frozen-DTO (`StreamEvent`, `Message`), бизнес-логики нет → тестировать нечего;
  оркестрация раннера покрыта через `ChatService` на `FakeAgentRunner` (Protocol-шов).
- **Отмена через обрыв соединения в середине SSE** (client-disconnect) — ограничение
  харнесса: `client` делит ОДНУ транзакционную сессию с телом теста, конкурентные
  запросы (открытый стрим + второй вызов / `gather`) падают «another operation is in
  progress» (задокументировано Ф2b, infra.md F2). Поэтому отмена покрыта через
  cancel-роут (последовательно) и через терминальные события в потоке, а не через
  реальный обрыв сокета на полпути. Семантика отмены раннера — за S3.
- **`get_chat` склейка artifacts по message_id в роуте** — покрыта на сервисном
  уровне (`set_message_id`-линковка) и smoke-уровне роута (история отдаётся);
  отдельный `ArtifactService` — скоуп S4 (projects/artifacts), не дублирую.

## Блокеры

Нет. Замороженную инфру не трогал; все правки — внутри `backend/tests/chat/`.
