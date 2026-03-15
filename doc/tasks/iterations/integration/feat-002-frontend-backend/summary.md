# Post-Implementation Summary: feat-002 — Frontend → Backend Connection

## Результат

Все mock-данные удалены из frontend API-модулей, заменены реальными HTTP-вызовами через axios. Настроен Vite dev proxy (`/api` → backend). MVP-авторизация (AuthGate) реализована. Project CRUD UI (rename/delete) добавлен. SSE-стриминг переключён на реальный fetch. Все REST-потоки верифицированы E2E через Chrome.

## Отклонения от плана

### 1. AuthGate: защита от закрытия (адаптация под @base-ui/react)

**План:** `onEscapeKeyDown={e => e.preventDefault()}`, `onPointerDownOutside={e => e.preventDefault()}` на `DialogContent`.

**Факт:** Dialog использует `@base-ui/react` (не Radix). Защита реализована через:
- `open` prop (controlled) — модалка не закрывается, пока username пуст
- `disablePointerDismissal` — блокирует закрытие по клику вне
- `onOpenChange={() => {}}` — пустой handler предотвращает закрытие по Escape
- `showCloseButton={false}` — нет крестика

Результат тот же — модалку нельзя закрыть без ввода имени.

### 2. ProjectCard: обёртка div вместо sibling

**План:** `ProjectActions` как sibling к NavLink (абсолютно позиционированный).

**Факт:** NavLink обёрнут в `div.group/card.relative`, ProjectActions внутри `div.absolute.right-1`. Это обеспечивает корректную работу `group-hover/card` для показа кнопки "..." и не требует `stopPropagation`.

### Правки по результатам ревью

3. **Delete redirect** — план предполагал `navigate("/")` всегда. После ревью: redirect только если удаляется текущий просматриваемый проект (`location.pathname.includes(/projects/${projectId})`). Иначе пользователь остаётся на текущем экране.

4. **Кнопка "..." pointer-events** — после ревью добавлены `pointer-events-none` в скрытом состоянии и `pointer-events-auto` при hover/focus-visible. Невидимая кнопка больше не перехватывает клики.

## E2E тесты (Chrome, реальный backend + PostgreSQL)

| Тест | Статус |
|------|--------|
| AuthGate: модалка, Escape не закрывает, ввод имени | PASS |
| Create project → появляется в sidebar | PASS |
| Sphere: GET (пустой) → Edit → PUT → rendered Markdown | PASS |
| Artifacts: GET (пустой список) | PASS |
| Rename project через "..." → PUT, sidebar обновляется | PASS |
| Home / Recents: загрузка с реального API | PASS |
| Delete project → подтверждение → DELETE, redirect на `/` | PASS |
| CORS: нет ошибок в консоли (Vite proxy) | PASS |

## Known Issues

- **cancelChat unhandled Promise** — `cancel()` в `useAgentStream` не обрабатывает rejected Promise от `cancelChat()`. Не регрессия (код не менялся). Scope feat-003.
- **SSE E2E** — `useAgentStream` переключён на реальный `fetch()`, но full flow не верифицирован (зависит от настроенного LLM agent). Scope feat-003.
- **downloadArtifact filename regex** — не обрабатывает `filename*=UTF-8''...` формат. Не проблема для текущего стека (FastAPI использует простой `filename=`).

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `frontend/vite.config.ts` | + `server.proxy` (`/api` → localhost:8000) |
| `frontend/src/shared/api/client.ts` | baseURL → `/api`, dynamic X-User-Name via interceptor, + `getUsername()`/`setUsername()` |
| `frontend/src/shared/api/projects.ts` | Удалены моки → реальные axios-вызовы |
| `frontend/src/shared/api/chats.ts` | Удалены моки + `mockSendMessage` → реальные axios-вызовы |
| `frontend/src/shared/api/sphere.ts` | Удалены моки → реальные axios-вызовы |
| `frontend/src/shared/api/artifacts.ts` | Удалены моки → реальные axios-вызовы, blob download |
| `frontend/src/app/components/AuthGate.tsx` | **Новый**: auth modal (Dialog, localStorage) |
| `frontend/src/App.tsx` | + AuthGate wrapper |
| `frontend/src/shared/ui/dropdown-menu.tsx` | **Новый**: shadcn DropdownMenu (install) |
| `frontend/src/features/projects/components/ProjectActions.tsx` | **Новый**: rename/delete dropdown + dialogs |
| `frontend/src/features/projects/components/ProjectCard.tsx` | + ProjectActions, div wrapper с group/card |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | `mockSendMessage` → real `fetch()` + error handling |
| `frontend/src/features/artifacts/components/ArtifactView.tsx` | `void downloadArtifact(...)` (async handling) |
