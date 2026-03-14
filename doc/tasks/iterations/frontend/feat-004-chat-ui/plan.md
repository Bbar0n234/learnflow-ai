# Implementation Plan: feat-004 — Chat UI

## Context

Итерация feat-004 — реализация интерфейса чата: список сообщений, рендеринг (user vs assistant), input с отправкой, auto-scroll. Работает на mock-данных, без реального стриминга (SSE — feat-005). После итерации — можно открыть чат, увидеть историю, "отправить" сообщение. Также реализуется список чатов на табе Chats в ProjectLayout и создание нового чата.

## Референсы

- [workflow.md](../../../../workflow.md) — процесс итерации
- [conventions.md](../../../tech/conventions.md) — git flow, именование, code quality
- [tasklist-frontend.md](../../tasklist-frontend.md) — состав работ и критерии приёмки
- [frontend.md](../../../tech/frontend.md) — экраны, компоненты, state, API-интеграция
- [backend.md](../../../tech/backend.md) — API-контракт, schemas
- [ADR-008](../../../tech/adr/ADR-008-frontend-stack.md) — обоснование стека

## Проверенные версии инструментов

| Инструмент | Версия | Источник проверки |
|-----------|--------|-------------------|
| TanStack Query | 5.90.21 | node_modules, exports: useQuery, useMutation, useQueryClient |
| React Router | 7.13.1 | node_modules, exports: useParams, useNavigate, Link, NavLink |
| Streamdown | 2.4.0 | node_modules, dist/index.d.ts — props: children, plugins, animated, isAnimating, mode |
| Zustand | 5.0.11 | node_modules, существующие stores подтверждают API |
| Tailwind CSS | 4.2.1 | node_modules, CSS-first конфиг |
| base-ui (shadcn) | 1.3.0 | node_modules, существующие компоненты |
| Vite | 7.3.1 | node_modules |

API всех инструментов совместимо с существующими паттернами в кодовой базе.

## Шаг 0 — Git

```bash
git fetch origin && git checkout -b feat/004-chat-ui origin/develop
```

Ветка `feat/004-chat-ui` — по conventions.md.

## Шаг 1 — Mock API: мутабельные чаты

**Файл:** `frontend/src/shared/api/chats.ts`

Сделать `MOCK_CHATS` мутабельным (`let` вместо `const`), чтобы `createChat` добавлял новый чат в список проекта. Аналогично паттерну из `projects.ts` (feat-003).

Изменения:
- `MOCK_CHATS` → `let` (или мутабельный массив внутри Record)
- `createChat()` → push новый `Chat` в `MOCK_CHATS[projectId]`, инициализировать массив если нет
- `getChat()` для несуществующего chatId — оставить текущий fallback `{ messages: [] }`

`MOCK_RECENT_CHATS` и `MOCK_CHAT_DETAIL` — оставить статичными. Для новых чатов getChat вернёт пустой messages, что корректно.

## Шаг 2 — TanStack Query хуки

Все хуки следуют паттерну из feat-003 (useProjects, useCreateProject).

### `features/chat/hooks/useChats.ts`
```typescript
useQuery({ queryKey: ["projects", projectId, "chats"], queryFn: () => getChats(projectId) })
```
Enabled только при наличии projectId.

### `features/chat/hooks/useChat.ts`
```typescript
useQuery({ queryKey: ["projects", projectId, "chats", chatId], queryFn: () => getChat(projectId, chatId) })
```
Enabled при наличии обоих ID.

### `features/chat/hooks/useCreateChat.ts`
```typescript
useMutation({
  mutationFn: ({ projectId, data }) => createChat(projectId, data),
  onSuccess: (_data, variables) => {
    queryClient.invalidateQueries({ queryKey: ["projects", variables.projectId, "chats"] });
    queryClient.invalidateQueries({ queryKey: ["chats", "recent"] });
  }
})
```
Инвалидация по таблице из frontend.md: `["projects", id, "chats"]` + `["chats", "recent"]`. Примечание: `projectId` берётся из `variables`, не из замыкания.

## Шаг 3 — Компоненты chat feature

### `features/chat/components/MessageItem.tsx`

Рендеринг одного сообщения. Два визуальных стиля:
- **user** — plain text, правый alignment (или left с отличающимся bg), без MarkdownRenderer
- **assistant** — MarkdownRenderer с `isStreaming={false}`, левый alignment, другой bg

Props: `{ message: Message }`. Тип Message из `shared/api/types.ts`.

Переиспользует: `MarkdownRenderer` из `shared/components/MarkdownRenderer.tsx`.

### `features/chat/components/MessageList.tsx`

Скроллируемый список сообщений с auto-scroll.

Props: `{ messages: Message[] }`.

Реализация:
- `overflow-auto flex-1` для скролла
- Маппинг messages → MessageItem
- `useRef` на div-якорь в конце списка
- `useEffect` → `bottomRef.current?.scrollIntoView({ behavior: 'smooth' })` при изменении `messages.length`

### `features/chat/components/ChatInput.tsx`

Textarea с отправкой.

Props: `{ onSend: (content: string) => void, disabled?: boolean }`.

Реализация:
- Textarea (shadcn/ui) с контролируемым state
- Отправка: Enter (без Shift) или кнопка Send (Lucide `SendHorizontal` иконка)
- Shift+Enter — перенос строки
- Очистка input после отправки
- Disabled state (для будущего isStreaming)

### `features/chat/components/ChatView.tsx`

Основной контейнер чата. Занимает всю доступную высоту.

Layout: `h-full flex flex-col` — MessageList (flex-1) + ChatInput (внизу).

Логика:
- `useParams()` → `id`, `cid`
- `useChat(id, cid)` → mock-данные с историей
- `useState<Message[]>([])` для локально добавленных сообщений
- `handleSend` → добавляет новый Message (role: "user", id: crypto.randomUUID(), created_at: now) в локальный state
- Отображает `[...data.messages, ...localMessages]`
- Loading/error states от useChat

### `features/chat/components/ChatList.tsx`

Список чатов проекта — замена `ProjectChatsStub`. Содержит input для создания нового чата (frontend.md:36,46 — "input для нового чата в этом проекте").

Props: нет (берёт projectId из `useParams()`).

Layout:
- Textarea/input сверху ("Start a new chat...") + кнопка Send
  - На submit: `useCreateChat` → `createChat({ projectId, data: { title: text } })` → `onSuccess: navigate(/projects/:id/chats/:newChatId)`
  - Введённый текст → title чата (первое сообщение через SSE в feat-005)
  - Enter (без Shift) или кнопка Send
- Список чатов → `useChats(projectId)` → карточки/ссылки (title, updated_at)
- Клик по чату → `Link` на `/projects/:id/chats/:cid`
- Loading/error/empty states

## Шаг 4 — ProjectLayout: корректировка Outlet-обёртки

**Файл:** `frontend/src/app/layouts/ProjectLayout.tsx`

Текущее:
```tsx
<div className="flex-1 overflow-auto p-6">
  <Outlet />
</div>
```

Проблема: `p-6` и `overflow-auto` мешают ChatView занять полную высоту и управлять собственным скроллом.

Изменение:
```tsx
<div className="flex-1 overflow-hidden">
  <Outlet />
</div>
```

Padding переносится в дочерние компоненты:
- ChatList — добавить `p-6 h-full overflow-auto`
- ChatView — собственный layout без внешнего padding (внутренний padding в MessageList и ChatInput)
- SphereStub, ArtifactsStub, ArtifactViewStub — добавить `p-6` обёртку (одна строка каждый)

## Шаг 5 — Router: замена стабов

**Файл:** `frontend/src/app/router.tsx`

```diff
- import { ProjectChatsStub } from "@/features/projects/components/ProjectChatsStub";
- import { ChatStub } from "@/features/chat/components/ChatStub";
+ import { ChatList } from "@/features/chat/components/ChatList";
+ import { ChatView } from "@/features/chat/components/ChatView";

  <Route index element={<ChatList />} />
  <Route path="chats/:cid" element={<ChatView />} />
```

## Шаг 6 — Sidebar: подключить New Chat

**Файл:** `frontend/src/app/components/Sidebar.tsx`

Текущая кнопка "New Chat" — disabled вне контекста проекта, no-op при клике.

Изменения:
- Импортировать `useCreateChat` и `useNavigate`
- На клик: `createChat({ projectId, data: {} })` → `onSuccess: navigate(/projects/:id/chats/:newChatId)`
- Disable во время мутации (`isPending`)

## Шаг 7 — Удаление стабов

Удалить файлы, заменённые реальными компонентами:
- `frontend/src/features/chat/components/ChatStub.tsx`
- `frontend/src/features/projects/components/ProjectChatsStub.tsx`

## Сводка файлов

### Новые (8)
| Файл | Назначение |
|------|-----------|
| `features/chat/hooks/useChats.ts` | Query: список чатов проекта |
| `features/chat/hooks/useChat.ts` | Query: детали чата (сообщения) |
| `features/chat/hooks/useCreateChat.ts` | Mutation: создание чата + инвалидация |
| `features/chat/components/ChatView.tsx` | Контейнер чата: MessageList + ChatInput |
| `features/chat/components/MessageList.tsx` | Скроллируемый список сообщений + auto-scroll |
| `features/chat/components/MessageItem.tsx` | Рендеринг сообщения (user/assistant) |
| `features/chat/components/ChatInput.tsx` | Textarea + Send |
| `features/chat/components/ChatList.tsx` | Список чатов проекта (замена ProjectChatsStub) |

### Модифицированные (7)
| Файл | Изменение |
|------|-----------|
| `shared/api/chats.ts` | Мутабельные моки для createChat |
| `app/layouts/ProjectLayout.tsx` | Убрать p-6/overflow-auto из Outlet-обёртки |
| `app/router.tsx` | Замена стабов на ChatList и ChatView |
| `app/components/Sidebar.tsx` | Подключить New Chat → createChat + navigate |
| `features/sphere/components/SphereStub.tsx` | Добавить p-6 обёртку |
| `features/artifacts/components/ArtifactsStub.tsx` | Добавить p-6 обёртку |
| `features/artifacts/components/ArtifactViewStub.tsx` | Добавить p-6 обёртку |

### Удаляемые (2)
| Файл |
|------|
| `features/chat/components/ChatStub.tsx` |
| `features/projects/components/ProjectChatsStub.tsx` |

## Ключевые решения

1. **Mock send** — добавляет только user message в локальный state компонента. Assistant response появится в feat-005 (SSE). Визуальное различие user/assistant демонстрируется существующими mock-сообщениями.

2. **Создание чата** — textarea/input в ChatList ("Start a new chat..."). Введённый текст → title чата, навигация в чат. В feat-005 текст станет первым сообщением, отправляемым через SSE. Sidebar "New Chat" — вторичный entry point с auto-title.

3. **Локальный state для новых сообщений** — `useState<Message[]>` в ChatView вместо мутации mock API. Простое решение, которое полностью заменяется SSE в feat-005.

4. **ProjectLayout padding** — переносится в дочерние компоненты. Необходимо для корректного flex-layout ChatView (фиксированный input внизу, скролл в MessageList).

## Верификация

1. `make dev-fe` — dev-сервер запускается
2. Навигация `/projects/proj-1` → таб Chats → список чатов из mock-данных
3. Клик по чату → `/projects/proj-1/chats/chat-1a` → история mock-сообщений
4. User и assistant сообщения визуально различаются
5. Assistant-сообщения рендерят Markdown (заголовки, код, списки)
6. Ввод текста в ChatInput → Enter/Send → сообщение появляется в списке
7. Auto-scroll к новому сообщению
8. "New Chat" из ChatList → создание чата → навигация → пустой чат
9. "New Chat" из Sidebar → то же поведение
10. Табы Sphere/Artifacts — по-прежнему работают (padding)
11. `make lint-fe` — 0 ошибок
12. `make format-fe` — 0 ошибок
13. TypeScript strict — 0 ошибок

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
