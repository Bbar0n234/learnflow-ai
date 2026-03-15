# Post-Implementation Summary: fix-001 — Contract Alignment

## Результат

Все три проблемы из pre-integration аудита устранены. Backend и frontend контракты согласованы.

## Отклонения от плана

### Допустимые адаптации

1. **`SSEEvent.done` в types.ts** — `message_id?: string` (optional) вместо always-string из плана. Backend отправляет `{"message_id": ""}` при отсутствии артефактов. Frontend обрабатывает оба случая одинаково (пустая строка и undefined — оба falsy).

2. **Mock artifact details** — добавлен `message_id` в mock объекты `ArtifactDetail` (artifacts.ts). Не было в плане, но необходимо для компиляции TypeScript после добавления `message_id` в интерфейс.

3. **`ChatView.tsx`** — добавлен `artifacts: []` к оптимистичному user-сообщению. Необходимо для соответствия обновлённому типу `Message`.

### Правки по результатам ревью

4. **Mock artifact binding** — `mockSendMessage` изначально добавлял assistant message с `artifacts: []`. После ревью исправлено: mock теперь привязывает созданный артефакт к `assistantMsg.artifacts`, корректно воспроизводя поведение реального backend (post-hoc linking → artifacts в finalized message).

5. **Inline type assertions** — заменены `[] as { id: string; ... }[]` на `[] as Artifact[]` с импортом типа. Устранено дублирование определения типа.

## Верифицированные потенциальные риски

1. **`artifact_created` event data shape** — `msg.artifact` из `create_artifact` tool содержит `id`. Подтверждено E2E тестами: SSE events содержали корректные `id`, post-hoc linking сработал.

2. **Post-hoc linking commit** — `set_message_id()` делает `flush()`, commit происходит в `get_db_session` middleware после завершения `StreamingResponse`. Подтверждено E2E: `GET /artifacts/{id}` вернул заполненный `message_id`.

## E2E тесты

### Backend (реальный backend + LLM)

| Тест | Статус |
|------|--------|
| E2E-1: Artifact → message binding (happy path) | PASS |
| E2E-2: Множественные артефакты в одном стриме | PASS |
| E2E-3: Message timestamps | PASS |
| E2E-4: Стрим без артефактов | PASS |
| E2E-5: Error handling (SSE contract) | SKIP — требует отключения LLM |
| E2E-6: Nullable fields (artifact без thread) | SKIP — нет DELETE endpoint для ThreadView |
| E2E-7: REST contract (create response types) | PASS |

### Frontend (mock mode, Chrome)

| Тест | Статус |
|------|--------|
| FE-1: Artifact cards в финализированном чате | PASS |
| FE-2: Streaming → finalized artifact cards | PASS |
| FE-3: TypeScript strict (0 ошибок, нет лишних типов) | PASS |
| FE-4: Create project/chat (полные типы) | PASS |

## Затронутые файлы

### Backend

| Файл | Изменение |
|------|-----------|
| `backend/app/models/artifact.py` | + `message_id` field |
| `backend/app/repositories/artifact.py` | + `set_message_id()`, `list_by_thread()` |
| `backend/app/services/artifact.py` | + `list_by_thread()` |
| `backend/app/services/agent_runner.py` | + `get_last_ai_message_id()` в Protocol |
| `backend/app/agent/runner.py` | + `get_last_ai_message_id()`, timestamps в messages, убран yield done |
| `backend/app/agent/graph.py` | + `created_at` в `additional_kwargs` после LLM-вызова |
| `backend/app/services/chat.py` | + `artifact_repo` dep, post-hoc linking, emit done с message_id |
| `backend/app/api/deps.py` | + `ArtifactRepository` в `get_chat_service()` |
| `backend/app/api/schemas/chats.py` | + `artifacts` в `MessageOut` |
| `backend/app/api/schemas/artifacts.py` | + `message_id` в `ArtifactDetailResponse` |
| `backend/app/api/routes/chats.py` | + артефакты в GET chat detail |
| `backend/alembic/versions/6b69e2cad2ae_*.py` | Миграция: ADD COLUMN message_id + index |

### Frontend

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/types.ts` | nullable fields, `Message.artifacts`, удалены `*CreateResponse` |
| `frontend/src/shared/api/projects.ts` | `createProject` → `Promise<Project>` |
| `frontend/src/shared/api/chats.ts` | `createChat` → `Promise<Chat>`, mock artifact binding |
| `frontend/src/shared/api/artifacts.ts` | fallback `thread_id: null`, `message_id` в mocks |
| `frontend/src/stores/stream-store.ts` | `StreamingArtifact.artifact_type` → `type` |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | маппинг `artifact_type` → `type` |
| `frontend/src/features/chat/components/ArtifactCard.tsx` | prop `artifact_type` → `type` |
| `frontend/src/features/chat/components/MessageItem.tsx` | + `projectId` prop, рендеринг artifact cards |
| `frontend/src/features/chat/components/ChatView.tsx` | `artifacts: []` в оптимистичном message |

### Документация

| Файл | Изменение |
|------|-----------|
| `doc/tech/backend.md` | POST responses с `updated_at`, nullable fields, artifacts в messages, Artifact model |
