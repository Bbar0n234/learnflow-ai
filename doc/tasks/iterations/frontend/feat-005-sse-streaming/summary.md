# Post-Implementation Summary: feat-005 — SSE Streaming

## Результат

Все критерии приёмки выполнены:
- Отправка сообщения инициирует mock SSE stream (ReadableStream, эмулирующий SSE-события 1:1 с backend.md)
- Текст появляется инкрементально (чанк за чанком), не целиком
- При `tool_start` отображается ToolIndicator (Loader2 + имя tool), при `tool_end` — скрывается
- При `artifact_created` в чате появляется ArtifactCard (transient, см. Known Limitations)
- Cancel прерывает стрим, UI возвращается в idle-состояние
- После `done` — chat query инвалидируется, полное сообщение из mock-данных
- Ошибки SSE (`error` event) отображаются пользователю (блок `text-destructive`)
- TypeScript strict — 0 ошибок, ESLint — 0 ошибок

Верификация: автоматическая (Claude in Chrome — кейсы 1, 6) + ручная архитектором (кейсы 2–5, 7).

## Отклонения от плана

### useAgentStream: referential stability для options

**Что:** план описывал `options` в массиве зависимостей `useCallback`. Ревью выявил антипаттерн — `options` создаётся inline в ChatView каждый рендер, вызывая пересоздание `send`. Исправлено через `useRef` паттерн: `optionsRef.current = options`, callbacks читают через ref.

**Вывод:** идиоматический React-паттерн для стабильных callbacks с доступом к свежим значениям.

### useAgentStream: точечная обработка ошибок в catch

**Что:** план предполагал generic `catch` для AbortError. Ревью указал, что это глотает все ошибки (JSON.parse, runtime). Реализовано различение: `AbortError` → ignore, остальное → `console.error` + `endStream()`.

**Вывод:** предотвращает скрытые баги при переходе на реальный бэкенд.

### useAgentStream: endStream() в cleanup при unmount

**Что:** план описывал только `abort()` в useEffect cleanup. Ревью выявил, что без `endStream()` store остаётся в `isStreaming=true` при unmount. Добавлен `endStream()` после `abort()`.

**Вывод:** гарантирует консистентность Zustand store при навигации.

### cancelChat: apiClient не используется в mock

**Что:** план предполагал `apiClient.post()` для cancelChat. Mock-реализация обходится внутренним Set без HTTP-вызова. Импорт `apiClient` закомментирован с TODO.

**Вывод:** при интеграции с бэкендом — раскомментировать import, заменить mock на реальный вызов.

## Known Limitations

### ArtifactCard — transient indicator

**Проблема:** ArtifactCard видна только во время стрима (~0.5 сек). После `endStream()` `streamingArtifacts` очищается, карточка исчезает. Финальное сообщение (из query invalidation) — `{id, role, content, created_at}` без привязки к артефактам.

**Причина:** по backend.md `Artifact` привязан к `thread_id`, не к `message_id`. GET chat detail возвращает messages без артефактов. Решение требует изменения контракта бэкенда (добавить `artifacts[]` в Message response или `message_id` в Artifact).

**Решение:** отложено до интеграции с бэкендом. Обсуждены 4 варианта (A–D), выбран D (known limitation).

### Mock artifact не добавляется в mock-хранилище artifacts.ts

**Проблема:** `artifact_created` SSE-событие эмитится, инвалидация `["projects", id, "artifacts"]` происходит, но mock artifacts store не обновляется — refetch возвращает те же данные.

**Причина:** связность mock-модулей (chats.ts → artifacts.ts) не оправдана для mock-фазы. Оба мока удаляются при интеграции с бэкендом.

## Созданные файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/features/chat/hooks/useAgentStream.ts` | SSE streaming хук: парсинг, store update, query invalidation |
| `frontend/src/features/chat/components/ToolIndicator.tsx` | Индикатор вызова tool (Loader2 + имя) |
| `frontend/src/features/chat/components/ArtifactCard.tsx` | Карточка артефакта inline в чате |

## Модифицированные файлы

| Файл | Изменение |
|------|-----------|
| `frontend/src/stores/stream-store.ts` | + `StreamingArtifact` тип, `streamingArtifacts[]`, `addArtifact()` |
| `frontend/src/shared/components/MarkdownRenderer.tsx` | + `mode="streaming"/"static"` prop |
| `frontend/src/shared/api/chats.ts` | + `cancelChat()`, `mockSendMessage()` (полная SSE-эмуляция) |
| `frontend/src/features/chat/components/ChatView.tsx` | Интеграция useAgentStream, подписка на stream-store |
| `frontend/src/features/chat/components/MessageList.tsx` | Streaming message, ToolIndicator, ArtifactCard, stream error, auto-scroll |
| `frontend/src/features/chat/components/ChatInput.tsx` | Cancel button (Square icon), disabled во время стрима |

## Актуализация документации

- **frontend.md** — добавлены `streamingArtifacts` и `addArtifact` в Stream Store (секция State Management). Остальная документация актуальна, архитектурных отклонений нет.
