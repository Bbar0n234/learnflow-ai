# Post-Implementation Summary: feat-004 — Chat UI

## Результат

Все критерии приёмки выполнены:
- Переход в чат (`/projects/:id/chats/:cid`) рендерит историю mock-сообщений (4 сообщения в chat-1a)
- User-сообщения: тёмный фон (`bg-primary`), правый alignment; assistant: светлый (`bg-muted`), левый
- Assistant-сообщения рендерят Markdown через MarkdownRenderer: заголовки, bold, списки, code с подсветкой синтаксиса, math ($E=mc^2$), Mermaid-диаграммы
- Input: Enter отправляет, Shift+Enter — перенос строки, input очищается после отправки
- Auto-scroll к новому сообщению работает (useEffect + scrollIntoView)
- Создание чата из ChatList: ввод текста → title → navigate в новый пустой чат
- Создание чата из Sidebar "New Chat": createChat с auto-title → navigate
- Табы Sphere/Artifacts работают корректно после переноса padding
- TypeScript strict — 0 ошибок, ESLint — 0 ошибок

Верификация проведена через Claude in Chrome: все 9 визуальных кейсов пройдены.

## Отклонения от плана

### MOCK_CHATS: const вместо let

**Что:** план предлагал `MOCK_CHATS` → `let` по аналогии с `mockProjects` из projects.ts. Реализация оставила `const`, т.к. `Record<string, Chat[]>` мутабелен через push/assignment на ключи без переприсвоения переменной. Это соответствует альтернативе из плана: "или мутабельный массив внутри Record".

**Вывод:** `const` корректнее семантически — переменная не переприсваивается, мутируется только содержимое. Отличие от `projects.ts`, где `let` нужен для `filter()` в `deleteProject()` (создаёт новый массив).

### ChatList — новый компонент вне Module Structure

**Что:** `ChatList` (список чатов проекта, замена `ProjectChatsStub`) не был указан в Module Structure секции frontend.md. Компонент логически принадлежит `features/chat/components/`, т.к. отображает чаты, а не проекты.

**Решение:** добавлен `ChatList` в Module Structure frontend.md.

## Созданные файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/features/chat/hooks/useChats.ts` | Query: список чатов проекта |
| `frontend/src/features/chat/hooks/useChat.ts` | Query: детали чата (сообщения) |
| `frontend/src/features/chat/hooks/useCreateChat.ts` | Mutation: создание чата + инвалидация |
| `frontend/src/features/chat/components/ChatView.tsx` | Контейнер чата: MessageList + ChatInput |
| `frontend/src/features/chat/components/MessageList.tsx` | Скроллируемый список сообщений + auto-scroll |
| `frontend/src/features/chat/components/MessageItem.tsx` | Рендеринг сообщения (user/assistant) |
| `frontend/src/features/chat/components/ChatInput.tsx` | Textarea + Send (Enter/кнопка) |
| `frontend/src/features/chat/components/ChatList.tsx` | Список чатов проекта + input нового чата |

## Модифицированные файлы

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/chats.ts` | createChat мутирует MOCK_CHATS (push + init массива) |
| `frontend/src/app/layouts/ProjectLayout.tsx` | Outlet-обёртка: `overflow-auto p-6` → `overflow-hidden`, padding в дочерних |
| `frontend/src/app/router.tsx` | ProjectChatsStub → ChatList, ChatStub → ChatView |
| `frontend/src/app/components/Sidebar.tsx` | New Chat: useCreateChat + useNavigate, isPending disable |
| `frontend/src/features/sphere/components/SphereStub.tsx` | Добавлен `p-6` (компенсация переноса padding из ProjectLayout) |
| `frontend/src/features/artifacts/components/ArtifactsStub.tsx` | Добавлен `p-6` |
| `frontend/src/features/artifacts/components/ArtifactViewStub.tsx` | Добавлен `p-6` |

## Удалённые файлы

| Файл | Причина |
|------|---------|
| `frontend/src/features/chat/components/ChatStub.tsx` | Заменён на ChatView |
| `frontend/src/features/projects/components/ProjectChatsStub.tsx` | Заменён на ChatList |

## Актуализация документации

- **frontend.md** — добавлен `ChatList` в Module Structure (секция `chat/components/`). Остальная документация актуальна, архитектурных отклонений нет.
