# Implementation Plan: integration/feat-001 — Backend Internal Wiring

## Референсы

- [workflow.md](../../../../workflow.md) — процесс итераций
- [conventions.md](../../../tech/conventions.md) — ветки, коммиты, code quality
- [tasklist-integration.md](../../tasklist-integration.md) — исходный таск-лист
- [backend.md](../../../tech/backend.md) — архитектура, API, SSE protocol, Service Layer

## Context

`feat-001: Backend Internal Wiring` — первая итерация integration scope. Цель: убедиться, что Service Layer использует реальные реализации из Agent Runtime (не стабы), и подтвердить это smoke-тестами через API.

**Результат исследования кода:** wiring уже реализован в ходе итераций backend-core и agent:
- `deps.py:63-67` — `ChatService` получает `request.app.state.agent_runner` (это `LangGraphAgentRunner`)
- `deps.py:70-71` — `LangGraphSphereService` получает `request.app.state.store`
- `main.py:31-98` — lifespan создаёт реальный LangGraph граф, checkpointer, store и `LangGraphAgentRunner`

Единственный мёртвый код — `StubAgentRunner` в `services/agent_runner.py:51-69`, реэкспортируемый через `services/__init__.py`.

## Быстро меняющиеся инструменты

Таблица из tasklist-integration.md: Docker, Vite proxy, FastAPI CORS.

Для `feat-001` эти инструменты **не затрагиваются** — итерация не включает изменений конфигурации Docker, Vite или CORS. FastAPI CORS уже настроен (`config.py:17-20`). Проверка актуальности этих инструментов откладывается до итераций, где они непосредственно нужны (feat-002 для Vite proxy, feat-004 для Docker).

## Шаги реализации

### Шаг 0. Создание ветки

```bash
git fetch origin && git checkout -b feat/001-backend-wiring origin/develop
```

### Шаг 1. Верификация wiring (code review)

Подтвердить, что в production-коде нигде не используется `StubAgentRunner`:

- `backend/app/api/deps.py` — `get_chat_service()` берёт `request.app.state.agent_runner` (= `LangGraphAgentRunner`)
- `backend/app/api/deps.py` — `get_sphere_service()` возвращает `LangGraphSphereService`
- `backend/app/main.py` — lifespan создаёт `LangGraphAgentRunner(graph)` и кладёт в `app.state`
- Нигде в `backend/app/` нет `import StubAgentRunner` (кроме `services/__init__.py` re-export)

**Статус: подтверждено** (grep показал, что StubAgentRunner используется только в `services/agent_runner.py` и `services/__init__.py`).

### Шаг 2. Smoke-тесты через curl

Предусловия: PostgreSQL запущен (`make docker-up`), миграции выполнены (`make migrate`), backend запущен (`make dev`). `.env` и `.env.local` настроены с валидным `LLM_API_KEY`.

#### 2.1 Создать проект
```bash
curl -s -X POST http://localhost:8000/projects/ \
  -H "Content-Type: application/json" \
  -H "X-User-Name: test-user" \
  -d '{"name": "Smoke Test Project"}' | jq .
```
Ожидание: `{ id: UUID, name: "Smoke Test Project", created_at: ... }`

#### 2.2 Создать чат
```bash
curl -s -X POST http://localhost:8000/projects/{PROJECT_ID}/chats \
  -H "Content-Type: application/json" \
  -H "X-User-Name: test-user" \
  -d '{"title": "Smoke Test Chat"}' | jq .
```
Ожидание: `{ thread_id: UUID, title: "Smoke Test Chat", created_at: ... }`

#### 2.3 Отправить сообщение → SSE stream
```bash
curl -s -N -X POST http://localhost:8000/projects/{PROJECT_ID}/chats/{CHAT_ID}/messages \
  -H "Content-Type: application/json" \
  -H "X-User-Name: test-user" \
  -d '{"content": "Hello, what can you do?"}'
```
Ожидание: SSE-поток с `text_chunk` событиями от реального LLM, завершающийся `done`.

#### 2.4 GET sphere
```bash
curl -s http://localhost:8000/projects/{PROJECT_ID}/sphere \
  -H "X-User-Name: test-user" | jq .
```
Ожидание: `{ project_id: UUID, content: str, updated_at: datetime }`

#### 2.5 PUT sphere → GET sphere
```bash
curl -s -X PUT http://localhost:8000/projects/{PROJECT_ID}/sphere \
  -H "Content-Type: application/json" \
  -H "X-User-Name: test-user" \
  -d '{"content": "## Test Section\n\n_Description_\n\nContent."}' | jq .
```
Затем повторный GET — content должен отражать изменения.

#### 2.6 Проверка persistence диалога
Отправить второе сообщение в тот же чат и затем получить историю:
```bash
curl -s http://localhost:8000/projects/{PROJECT_ID}/chats/{CHAT_ID} \
  -H "X-User-Name: test-user" | jq .messages
```
Ожидание: массив сообщений содержит оба сообщения пользователя и ответы ассистента.

### Шаг 3. Удаление мёртвого кода

#### 3.1 `backend/app/services/agent_runner.py`
Удалить класс `StubAgentRunner` (строки 51-69).

#### 3.2 `backend/app/services/__init__.py`
Убрать `StubAgentRunner` из импорта (строка 1) и из `__all__` (строка 24).

### Шаг 4. Проверка качества кода

```bash
make lint && make type-check
```

Оба должны пройти без ошибок.

### Шаг 5. Обновление документации

Обновить `doc/tasks/tasklist-integration.md`:
- Статус `feat-001` → `✅ Done` в overview-таблице
- Статус в разделе итерации → `✅ Done`
- Отметить чекбоксы в составе работ и критериях приёмки

### Шаг 6. Ревью архитектора

Дождаться обратной связи от архитектора перед коммитом и пушем.

## Критерии приёмки (из tasklist)

- [ ] POST /messages возвращает SSE-поток с реальными text_chunk от LLM
- [ ] GET /sphere возвращает Knowledge Sphere из LangGraph Store
- [ ] PUT /sphere записывает данные в Store, повторный GET отражает изменения
- [ ] Диалог сохраняется: повторный запрос в тот же чат видит историю
- [ ] `make lint && make type-check` проходят

## Файлы для изменения

| Файл | Изменение |
|------|-----------|
| `backend/app/services/agent_runner.py` | Удалить `StubAgentRunner` (строки 51-69) |
| `backend/app/services/__init__.py` | Убрать `StubAgentRunner` из импорта и `__all__` |
| `doc/tasks/tasklist-integration.md` | Обновить статус feat-001 → Done |
