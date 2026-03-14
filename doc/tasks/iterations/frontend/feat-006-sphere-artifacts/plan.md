# Implementation Plan: feat-006 — Sphere + Artifacts

## Context

Последняя feature-итерация фронтенда. Все предыдущие фичи (scaffold, shared infra, sidebar, chat UI, SSE streaming) завершены. Осталось реализовать Knowledge Sphere (просмотр/редактирование) и Artifacts (список, просмотр, скачивание). После итерации — все feature-модули из frontend.md реализованы, фронтенд MVP-complete.

## Референсы

- **Спецификация:** [doc/tech/frontend.md](../../doc/tech/frontend.md) — экраны, компоненты, state, API
- **API-контракт:** [doc/tech/backend.md](../../doc/tech/backend.md) — endpoints, schemas, SSE
- **ADR:** [doc/tech/adr/ADR-008-frontend-stack.md](../../doc/tech/adr/ADR-008-frontend-stack.md) — обоснование стека
- **Conventions:** [doc/tech/conventions.md](../../doc/tech/conventions.md) — git, code quality, именование
- **Workflow:** [doc/workflow.md](../../doc/workflow.md) — итерации, жизненный цикл
- **Tasklist:** [doc/tasks/tasklist-frontend.md](../../doc/tasks/tasklist-frontend.md) — feat-006

## Верификация версий инструментов

Установленные версии проверены через `package.json` и `node_modules`:

| Инструмент | Установлен | API подтверждён через |
|-----------|-----------|----------------------|
| TanStack Query | 5.90.21 | Существующие хуки (useChats, useChat, useCreateChat) |
| React Router | 7.13.1 | Существующие компоненты (router.tsx, ProjectLayout) |
| Streamdown | 2.4.0 | MarkdownRenderer.tsx |
| shadcn/ui | 4.0.5 (style: base-nova) | shared/ui/*.tsx |
| Tailwind CSS | 4.2.1 | Существующие компоненты |
| Zustand | 5.0.11 | Не затрагивается (нет новых stores) |

## Существующие ресурсы для переиспользования

| Ресурс | Путь | Как используется |
|--------|------|-----------------|
| API sphere.ts (mock) | `src/shared/api/sphere.ts` | getSphere, updateSphere — **требуют доработки** (шаг 1) |
| API artifacts.ts (mock) | `src/shared/api/artifacts.ts` | getArtifacts, getArtifact, downloadArtifact — **требуют доработки** (шаг 1) |
| Типы | `src/shared/api/types.ts` | Sphere, Artifact, ArtifactDetail, UpdateSphereRequest — готовы |
| MarkdownRenderer | `src/shared/components/MarkdownRenderer.tsx` | Viewer для sphere и artifacts |
| apiClient | `src/shared/api/client.ts` | baseURL для download URL |
| shadcn/ui | `src/shared/ui/` | Button, Textarea, ScrollArea — все нужные примитивы есть |
| Паттерн useQuery | `src/features/chat/hooks/useChat.ts` | Образец для useSphere, useArtifact |
| Паттерн useMutation | `src/features/chat/hooks/useCreateChat.ts` | Образец для useUpdateSphere |
| Паттерн списка | `src/features/chat/components/ChatList.tsx` | Образец для ArtifactList |
| ArtifactCard | `src/features/chat/components/ArtifactCard.tsx` | Паттерн отображения артефакта |

## План реализации

### Шаг 0: Создание ветки

```bash
git fetch origin && git checkout -b feat/006-sphere-artifacts origin/develop
```

Ветка согласно conventions.md: `<type>/<NNN>-<short-desc>`.

---

### Шаг 1: Доработка mock-данных

Три проблемы в существующих mock-модулях, блокирующие acceptance criteria.

**Файл:** `src/shared/api/sphere.ts` — **редактирование**

Проблема: `updateSphere()` возвращает обновлённый объект, но не мутирует `MOCK_SPHERE`. После инвалидации `getSphere()` вернёт старые данные → цикл Viewer → Editor → Save → Viewer не работает.

Исправление: в `updateSphere()` добавить `MOCK_SPHERE[projectId] = updated` перед return. Это обеспечит персистентность изменений в рамках сессии.

**Файл:** `src/shared/api/artifacts.ts` — **редактирование**

Проблема 1: `art-2` ("Consensus Algorithms Comparison") есть в `MOCK_ARTIFACTS["proj-1"]`, но отсутствует в `MOCK_ARTIFACT_DETAILS`. `getArtifact("proj-1", "art-2")` вернёт fallback "Unknown artifact" с пустым content → сценарий "клик по артефакту → контент рендерится" не пройдёт.

Исправление: добавить запись `"art-2"` в `MOCK_ARTIFACT_DETAILS` с контентом о консенсус-алгоритмах (Raft vs Paxos, таблица сравнения).

Проблема 2: `downloadArtifact()` использует `console.log` вместо `window.open`. Критерий приёмки требует "корректный URL на download endpoint" ([tasklist-frontend.md:230], [frontend.md:197]).

Исправление: заменить `console.log` на `window.open` с корректно сформированным URL: `${apiClient.defaults.baseURL}/projects/${projectId}/artifacts/${artifactId}/download?format=${format}`. Без бэкенда откроется ошибка — ожидаемо, URL корректен. Добавить import `apiClient` из `./client`.

---

### Шаг 2: Sphere — хуки (data layer)

**Файлы:**
- `src/features/sphere/hooks/useSphere.ts` — **новый**
- `src/features/sphere/hooks/useUpdateSphere.ts` — **новый**

**useSphere.ts:**
```
useQuery({
  queryKey: ["projects", projectId, "sphere"],
  queryFn: () => getSphere(projectId!),
  enabled: !!projectId,
})
```
Query key из frontend.md: `["projects", id, "sphere"]`.

**useUpdateSphere.ts:**
```
useMutation({
  mutationFn: ({ projectId, data }) => updateSphere(projectId, data),
  onSuccess: (_, variables) => {
    queryClient.invalidateQueries({
      queryKey: ["projects", variables.projectId, "sphere"],
    });
  },
})
```
Инвалидация из frontend.md: `Обновить sphere → ["projects", id, "sphere"]`.

---

### Шаг 3: Artifacts — хуки (data layer)

**Файлы:**
- `src/features/artifacts/hooks/useArtifacts.ts` — **новый**
- `src/features/artifacts/hooks/useArtifact.ts` — **новый**

**useArtifacts.ts:**
```
useQuery({
  queryKey: ["projects", projectId, "artifacts"],
  queryFn: () => getArtifacts(projectId!),
  enabled: !!projectId,
})
```

**useArtifact.ts:**
```
useQuery({
  queryKey: ["projects", projectId, "artifacts", artifactId],
  queryFn: () => getArtifact(projectId!, artifactId!),
  enabled: !!projectId && !!artifactId,
})
```

---

### Шаг 4: Sphere — компоненты (UI layer)

**Файлы:**
- `src/features/sphere/components/SphereViewer.tsx` — **новый**
- `src/features/sphere/components/SphereEditor.tsx` — **новый**
- `src/features/sphere/components/SphereView.tsx` — **новый** (контейнер)

**SphereViewer** — отображение content через MarkdownRenderer в ScrollArea. Кнопка "Edit" (Pencil icon) для переключения в режим редактирования. При пустом content — placeholder.

**SphereEditor** — Textarea с текущим content, кнопки Save и Cancel. Save вызывает useUpdateSphere mutation. При успехе — callback на переключение в viewer.

**SphereView** — контейнер, управляет состоянием `isEditing: boolean`. Загружает данные через useSphere. Рендерит SphereViewer или SphereEditor в зависимости от режима. Обрабатывает loading/error.

> Контейнер SphereView не указан явно в frontend.md, но необходим для управления toggle-состоянием. Следует паттерну ChatView (контейнер + дочерние компоненты).

---

### Шаг 5: Artifacts — компоненты (UI layer)

**Файлы:**
- `src/features/artifacts/components/ArtifactList.tsx` — **заменяет ArtifactsStub**
- `src/features/artifacts/components/ArtifactView.tsx` — **заменяет ArtifactViewStub**

**ArtifactList** — список артефактов проекта. useArtifacts хук. Loading/error/empty states. Каждый элемент — ссылка (`Link`) на `/projects/:id/artifacts/:aid`. Отображает: иконка, title, type, дата. Паттерн из ChatList.

**ArtifactView** — просмотр артефакта. useArtifact хук. Заголовок, тип, дата создания. Контент через MarkdownRenderer (mode="static"). Две кнопки скачивания: Download MD, Download PDF. Download вызывает `downloadArtifact(projectId, artifactId, format)` — откроет `window.open` с корректным URL. Кнопка "Back to artifacts" — навигация назад.

---

### Шаг 6: Обновление роутера и удаление стабов

**Файл:** `src/app/router.tsx` — **редактирование**

Замены:
- `SphereStub` → `SphereView` (из `@/features/sphere/components/SphereView`)
- `ArtifactsStub` → `ArtifactList` (из `@/features/artifacts/components/ArtifactList`)
- `ArtifactViewStub` → `ArtifactView` (из `@/features/artifacts/components/ArtifactView`)

Удалить старые импорты стабов.

**Удалить файлы:**
- `src/features/sphere/components/SphereStub.tsx`
- `src/features/artifacts/components/ArtifactsStub.tsx`
- `src/features/artifacts/components/ArtifactViewStub.tsx`

---

### Шаг 7: Верификация

1. **Линтер + форматтер:** `make lint-fe && make format-fe` — без ошибок
2. **TypeScript:** `npx tsc -b` (или через `make build-fe` если есть) — без ошибок
3. **Ручное тестирование** (`make dev-fe`):
   - Таб Sphere → рендерит Knowledge Sphere из mock-данных
   - Кнопка Edit → SphereEditor с содержимым в textarea
   - Изменить текст → Save → вернуться в Viewer, **контент обновлён** (mock персистентность)
   - Cancel → вернуться в Viewer без изменений
   - Пустой sphere (новый проект) — placeholder
   - Таб Artifacts → список артефактов из mock-данных
   - Клик по **каждому** артефакту (art-1, art-2, art-3) → контент рендерится через MarkdownRenderer
   - Кнопки Download MD / PDF → `window.open` с корректным URL (новая вкладка, без бэкенда — ошибка, URL корректен)
   - Пустой список артефактов — empty state
   - Навигация между табами Chats / Sphere / Artifacts работает корректно

---

### Шаг 8: Ревью архитектора

Дождаться обратной связи от архитектора перед коммитом и пушем. Исправить замечания, если есть.

## Итоговая файловая структура изменений

```
ИЗМЕНЕНЫ (mock-данные):
  src/shared/api/sphere.ts       # updateSphere: персистентность в MOCK_SPHERE
  src/shared/api/artifacts.ts    # art-2 detail + downloadArtifact: window.open

НОВЫЕ:
  src/features/sphere/
  ├── components/
  │   ├── SphereView.tsx         # контейнер (toggle viewer/editor)
  │   ├── SphereViewer.tsx       # отображение sphere
  │   └── SphereEditor.tsx       # редактирование sphere
  └── hooks/
      ├── useSphere.ts           # query хук
      └── useUpdateSphere.ts     # mutation хук

  src/features/artifacts/
  ├── components/
  │   ├── ArtifactList.tsx       # заменяет ArtifactsStub.tsx
  │   └── ArtifactView.tsx       # заменяет ArtifactViewStub.tsx
  └── hooks/
      ├── useArtifacts.ts        # query хук
      └── useArtifact.ts         # query хук

ИЗМЕНЁН:
  src/app/router.tsx             # замена стабов на реальные компоненты

УДАЛЕНЫ:
  src/features/sphere/components/SphereStub.tsx
  src/features/artifacts/components/ArtifactsStub.tsx
  src/features/artifacts/components/ArtifactViewStub.tsx
```

Новых зависимостей нет. Новых shadcn/ui компонентов не требуется — Textarea, Button, ScrollArea уже установлены.
