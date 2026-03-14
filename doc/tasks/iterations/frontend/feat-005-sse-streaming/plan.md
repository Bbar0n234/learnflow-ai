# Implementation Plan: feat-005 — SSE Streaming

## Context

Итерация feat-005 — реализация real-time стриминга ответов агента через SSE. Самая технически сложная итерация фронтенда. Предыдущие итерации (feat-001..004) создали scaffold, shared infrastructure, sidebar, chat UI на mock-данных. Сейчас отправка сообщения просто добавляет user message в локальный state без ответа. feat-005 заменяет это на полноценный SSE-поток с инкрементальным рендерингом, tool-индикаторами, artifact-картами и cancel.

Бэкенд ещё не реализован — работаем на mock SSE (ReadableStream, эмулирующий SSE-события).

## Референсы

- **Состав работ и критерии приёмки:** `doc/tasks/tasklist-frontend.md` → feat-005
- **SSE Streaming Protocol:** `doc/tech/backend.md` → секция SSE Streaming Protocol
- **Frontend архитектура (SSE lifecycle, state, invalidation):** `doc/tech/frontend.md` → секции SSE-стриминг, State Management
- **Conventions:** `doc/tech/conventions.md` → ветки, коммиты, code quality
- **Workflow:** `doc/workflow.md` → жизненный цикл итерации
- **ADR-008:** `doc/tech/adr/ADR-008-frontend-stack.md` → fetch для SSE, Streamdown

## Проверка API инструментов

| Инструмент | Версия | Проверено | Релевантность для feat-005 |
|-----------|--------|-----------|---------------------------|
| Streamdown | 2.4.0 | inspect dist/index.d.ts | `mode="streaming"`, `animated`, `isAnimating` — OK |
| TanStack Query | 5.90.0 | inspect build/modern | `invalidateQueries({ queryKey })` — OK, паттерн из useCreateChat |
| Zustand | 5.0.11 | inspect, working stream-store | `create()`, `getState()` — OK |
| React Router | 7.13.1 | working code | `useParams`, `useNavigate` — без изменений |
| Tailwind CSS | 4.2.1 | working code | Утилитарные классы — без изменений |
| shadcn/ui | 4.0.5 | working code | Установленные компоненты достаточны |
| ESLint | 10.0.3 | `make lint-fe` | Финальная проверка |
| Vite | 7.3.1 | working code | Без изменений конфигурации |

## Ветка

```
git fetch origin && git checkout -b feat/005-sse-streaming origin/develop
```

## Шаги реализации

### Шаг 1. Расширить stream-store

**Файл:** `frontend/src/stores/stream-store.ts`

Добавить `streamingArtifacts` для отслеживания артефактов, созданных во время стрима. Необходимо для рендеринга ArtifactCard inline в чате.

```
streamStore
├── ...existing fields...
├── streamingArtifacts: StreamingArtifact[]   ← NEW
├── addArtifact(artifact)                      ← NEW
└── endStream() — обнулять streamingArtifacts  ← UPDATE
```

Тип `StreamingArtifact`: `{ id: string; title: string; artifact_type: string }`.

### Шаг 2. Обновить MarkdownRenderer

**Файл:** `frontend/src/shared/components/MarkdownRenderer.tsx`

Добавить `mode` prop из Streamdown API v2.4.0. При `isStreaming=true` передавать `mode="streaming"` — Streamdown корректно обрабатывает незакрытый Markdown mid-stream.

### Шаг 3. Добавить cancelChat и mock SSE в API-модуль

**Файл:** `frontend/src/shared/api/chats.ts`

**cancelChat(projectId, chatId):**
- `apiClient.post(\`/projects/${projectId}/chats/${chatId}/cancel\`)`
- Mock: ставит флаг отмены для chatId (shared state, доступный `mockSendMessage`), возвращает `{ ok: true }`

**mockSendMessage(projectId, chatId, content, abortSignal?):**
- Принимает `AbortSignal` для hard cleanup (unmount)
- **Инициализация:** если `MOCK_CHAT_DETAIL[chatId]` не существует — создать запись (title из `MOCK_CHATS`, пустой `messages[]`). Это покрывает flow создания нового чата (createChat добавляет только в MOCK_CHATS, не в MOCK_CHAT_DETAIL)
- Добавляет user message в `MOCK_CHAT_DETAIL[chatId].messages`
- Возвращает `ReadableStream<Uint8Array>`, эмулирующий SSE-события:
  1. Несколько `text_chunk` событий (фиксированный текст, разбитый на чанки с задержкой ~50ms)
  2. `tool_start` → задержка → `tool_end` (демонстрация tool use)
  3. Ещё `text_chunk` события
  4. `artifact_created` (демонстрация создания артефакта)
  5. `done`
- **Cancel handling:** между эмиссиями проверяет флаг отмены. Если установлен — эмитит `error` event с `detail: "Generation cancelled"`, закрывает стрим. Это эмулирует реальное поведение сервера: `POST /cancel` → сервер шлёт терминальный `error` event → стрим закрыт (backend.md:219)
- После `done` добавляет assistant message в `MOCK_CHAT_DETAIL[chatId].messages`
- При получении abort signal (unmount) — прекращает эмиссию без error event

Формат SSE-событий: `data: {"type": "...", ...}\n\n` — 1:1 с `backend.md` SSE Streaming Protocol.

### Шаг 4. Создать useAgentStream хук

**Файл:** `frontend/src/features/chat/hooks/useAgentStream.ts`

Кастомный хук — ядро итерации. Оркестрирует SSE-стрим, парсинг событий, обновление store, инвалидацию queries.

**Интерфейс:**
```typescript
interface UseAgentStreamOptions {
  onDone?: () => void;
  onError?: (detail: string) => void;
}

function useAgentStream(
  projectId: string,
  chatId: string,
  options?: UseAgentStreamOptions
): {
  send: (content: string) => void;
  cancel: () => void;
}
```

**Логика `send(content)`:**
1. `startStream(chatId)` через `useStreamStore.getState()` (императивный доступ, без подписки на state)
2. Создать `AbortController`, сохранить в ref
3. Вызвать `mockSendMessage(projectId, chatId, content, signal)` (→ TODO: заменить на `fetch()`)
4. Читать ReadableStream через `getReader()` + `TextDecoder`
5. Парсить SSE: разделить по `\n\n`, извлечь `data:` строки, `JSON.parse` → `SSEEvent`
6. Dispatch по типу события:
   - `text_chunk` → `appendText(content)`
   - `tool_start` → `setTool(tool)`
   - `tool_end` → `setTool(null)`
   - `artifact_created` → `addArtifact({id, title, artifact_type})` + `invalidateQueries(["projects", projectId, "artifacts"])`
   - `done` → `endStream()` + `invalidateQueries(["projects", projectId, "chats", chatId])` + `invalidateQueries(["chats", "recent"])` + `options.onDone?.()`
   - `error` → `endStream()` + `options.onError?.(detail)`

**Логика `cancel()`:**
Следует задокументированному lifecycle (frontend.md:195, backend.md:219): `POST /cancel → сервер шлёт error event → стрим закрыт`.
1. Установить `isCancelling` flag (ref) — чтобы отличить cancel от реальной ошибки
2. `cancelChat(projectId, chatId)` через axios — уведомить сервер (mock ставит cancel flag)
3. Не вызывать `abort()` и не вызывать `endStream()` вручную — mock/сервер эмитит `error` event → SSE parser обрабатывает его в нормальном потоке
4. В обработчике `error` event: если `isCancelling` — не вызывать `onError` (UI просто возвращается в idle), только `endStream()`

**Cleanup:** на unmount — `abort()` через useEffect cleanup (hard kill, отличается от cancel).

### Шаг 5. Создать ToolIndicator

**Файл:** `frontend/src/features/chat/components/ToolIndicator.tsx`

Простой компонент: `Loader2` иконка (анимированная) + имя tool. Tailwind-стилизация (inline flex, muted цвета, `animate-spin` на иконке).

```typescript
interface ToolIndicatorProps {
  toolName: string;
}
```

### Шаг 6. Создать ArtifactCard

**Файл:** `frontend/src/features/chat/components/ArtifactCard.tsx`

Карточка артефакта inline в чате. Показывает title, artifact_type badge. Ссылка на `/projects/:id/artifacts/:aid` (через `useParams` для projectId + artifact id из пропсов).

```typescript
interface ArtifactCardProps {
  artifact: { id: string; title: string; artifact_type: string };
  projectId: string;
}
```

### Шаг 7. Интегрировать стриминг в ChatView

**Файл:** `frontend/src/features/chat/components/ChatView.tsx`

Основные изменения:
1. Добавить `streamError` state (`string | null`) для ошибок SSE
2. Добавить `useAgentStream(id!, cid!, { onDone: () => setLocalMessages([]), onError: (detail) => setStreamError(detail) })`
3. Подписаться на stream-store: `useStreamStore(selector)` для `isStreaming`, `streamingText`, `activeTool`, `streamingArtifacts`, `streamingChatId`
4. Показывать streaming UI только если `streamingChatId === cid` (чтобы стрим не отображался в других чатах)
5. `handleSend`: очистить `streamError` + добавить user message в localMessages + вызвать `send(content)`
6. Передать `isStreaming`, `cancel`, `streamError` в дочерние компоненты

### Шаг 8. Обновить MessageList — показать streaming message

**Файл:** `frontend/src/features/chat/components/MessageList.tsx`

После списка обычных сообщений:

**Streaming message** (если `isStreaming`):
- Блок с assistant-стилизацией (`bg-muted`, тот же layout что MessageItem)
- `MarkdownRenderer` с `isStreaming={true}` для `streamingText`
- `ToolIndicator` если `activeTool` задан
- `ArtifactCard` для каждого элемента из `streamingArtifacts`

**Stream error** (если `streamError` задан и `!isStreaming`):
- Блок с `text-destructive` стилизацией после сообщений
- Текст ошибки из `streamError`
- Появляется когда SSE-стрим завершился с `error` event (кроме cancel — cancel не вызывает onError)

Новые пропсы: `isStreaming`, `streamingText`, `activeTool`, `streamingArtifacts`, `projectId`, `streamError`.

Auto-scroll: текущий `useEffect` с `[messages.length]` дополнить зависимостью от `streamingText` (или `isStreaming`) для скролла во время стрима.

### Шаг 9. Обновить ChatInput — cancel button

**Файл:** `frontend/src/features/chat/components/ChatInput.tsx`

- Новые пропсы: `isStreaming`, `onCancel`
- Когда `isStreaming=true`:
  - Textarea disabled
  - Кнопка Send заменяется на кнопку Cancel (иконка `Square` из Lucide — паттерн "stop generation")
  - Клик по Cancel → `onCancel()`
- Когда `isStreaming=false`:
  - Текущее поведение (Send)

### Шаг 10. Верификация

1. `npx tsc --noEmit` — TypeScript strict, 0 ошибок
2. `make lint-fe` — ESLint, 0 ошибок
3. `make format-fe` — Prettier
4. `make dev-fe` — dev server, ручная проверка:
   - Отправить сообщение → текст появляется инкрементально (чанк за чанком)
   - Во время tool_start → ToolIndicator с Loader2 + имя tool
   - После tool_end → ToolIndicator скрывается
   - При artifact_created → ArtifactCard появляется
   - Cancel → стрим прерывается, UI возвращается в idle
   - После done → chat query инвалидируется, полное сообщение из mock-данных
   - Ошибки SSE → отображение пользователю
   - Auto-scroll во время стриминга

### Шаг 11. Ревью архитектора

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

## Файлы

### Создаются
| Файл | Назначение |
|------|-----------|
| `frontend/src/features/chat/hooks/useAgentStream.ts` | SSE streaming hook |
| `frontend/src/features/chat/components/ToolIndicator.tsx` | Tool call indicator |
| `frontend/src/features/chat/components/ArtifactCard.tsx` | Artifact card inline in chat |

### Модифицируются
| Файл | Изменение |
|------|-----------|
| `frontend/src/stores/stream-store.ts` | + streamingArtifacts, addArtifact |
| `frontend/src/shared/components/MarkdownRenderer.tsx` | + mode prop (streaming/static) |
| `frontend/src/shared/api/chats.ts` | + cancelChat, mockSendMessage |
| `frontend/src/features/chat/components/ChatView.tsx` | Интеграция useAgentStream |
| `frontend/src/features/chat/components/MessageList.tsx` | Streaming message rendering |
| `frontend/src/features/chat/components/ChatInput.tsx` | Cancel button, disabled during streaming |

### Переиспользуемые (без изменений)
| Файл | Что используется |
|------|-----------------|
| `frontend/src/shared/api/types.ts` | SSEEvent, SendMessageRequest |
| `frontend/src/shared/api/client.ts` | apiClient для cancelChat |
| `frontend/src/features/chat/hooks/useChat.ts` | Query key pattern: ["projects", id, "chats", cid] |
| `frontend/src/features/chat/hooks/useCreateChat.ts` | Паттерн invalidateQueries |
| `frontend/src/features/chat/components/MessageItem.tsx` | Без изменений — рендерит только static messages |

## Архитектурные решения (вытекают из документации)

1. **fetch для SSE, axios для REST** — ADR-008, frontend.md
2. **stream-store для эфемерного state стрима** — frontend.md State Management
3. **Инвалидация queries по таблице** — frontend.md Mutations → инвалидация
4. **Mock SSE для автономной работы** — tasklist-frontend.md ("или mock SSE для автономной работы")
5. **`useStreamStore.getState()` для императивного доступа** — идиоматический Zustand паттерн (actions вызываются из async callback, не из render cycle)

## Вопросы к архитектору

Нет открытых вопросов — все решения однозначно следуют из документации.
