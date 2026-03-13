# Post-Implementation Summary: feat-002 — Shared Infrastructure

## Результат

Все критерии приёмки выполнены:
- API-модули экспортируют все функции из frontend.md (14 функций, 4 модуля)
- Моки возвращают типизированные данные, соответствующие backend schemas (runtime shape-проверка в Chrome console)
- Zustand stores работают: toggleSidebar переключает state, stream lifecycle (start → append → setTool → end) корректен
- MarkdownRenderer рендерит Markdown с подсветкой синтаксиса (Shiki), KaTeX-формулами и Mermaid-диаграммами
- Типы покрывают все сущности: Project, Chat, Message, Sphere, Artifact, SSE events + Request/Response типы
- TypeScript strict — 0 ошибок, ESLint — 0 ошибок, Vite production build — success

## Отклонения от плана

### @streamdown/math: singleDollarTextMath

**Что:** при runtime-верификации обнаружено, что дефолтный экспорт `math` из `@streamdown/math` не поддерживает inline-формулы с одинарным `$...$` (только `$$...$$`). Опция `singleDollarTextMath` по умолчанию `false`.

**Влияние:** в плане использовался `import { math } from "@streamdown/math"`. С дефолтными настройками формулы вида `$E = mc^2$` рендерились как plain text.

**Решение:** заменено на `createMathPlugin({ singleDollarTextMath: true })`. Inline math (`$...$`) и display math (`$$...$$`) работают корректно. Не влияет на архитектуру — локальное изменение в MarkdownRenderer.

### scroll-area.tsx: неиспользуемый import React

**Что:** shadcn CLI сгенерировал `scroll-area.tsx` с `import * as React from "react"`, который не используется в компоненте (base-ui стиль не требует `React` namespace).

**Решение:** удалён неиспользуемый import для прохождения TypeScript strict mode.

## Созданные файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/shared/api/client.ts` | axios instance с base URL и error interceptor |
| `frontend/src/shared/api/types.ts` | TypeScript типы 1:1 с backend schemas |
| `frontend/src/shared/api/projects.ts` | getProjects, getProject, createProject, updateProject, deleteProject |
| `frontend/src/shared/api/chats.ts` | getChats, getChat, createChat, getRecentChats |
| `frontend/src/shared/api/sphere.ts` | getSphere, updateSphere |
| `frontend/src/shared/api/artifacts.ts` | getArtifacts, getArtifact, downloadArtifact |
| `frontend/src/shared/components/MarkdownRenderer.tsx` | Streamdown обёртка (code + math + mermaid) |
| `frontend/src/shared/ui/dialog.tsx` | shadcn/ui Dialog |
| `frontend/src/stores/ui-store.ts` | Zustand UI store (sidebarOpen) |
| `frontend/src/stores/stream-store.ts` | Zustand stream store (SSE lifecycle) |

## Модифицированные файлы

| Файл | Изменение |
|------|-----------|
| `frontend/package.json` | Добавлены axios, zustand, streamdown, @streamdown/code, @streamdown/math, @streamdown/mermaid, katex |
| `frontend/package-lock.json` | Обновлён lock-файл |
| `frontend/src/index.css` | Добавлены `@source` директивы для streamdown и плагинов |
| `frontend/src/main.tsx` | Добавлены `import "streamdown/styles.css"` и `import "katex/dist/katex.min.css"` |
| `frontend/src/shared/ui/button.tsx` | Обновлён shadcn CLI при установке dialog |
| `frontend/src/shared/ui/scroll-area.tsx` | Удалён неиспользуемый `import * as React` |

## Актуализация документации

Отклонения не влияют на проектную архитектуру — все изменения локальные (конфигурация плагина, удаление unused import). Документация в `doc/tech/frontend.md` и `doc/tech/backend.md` актуальна, обновление не требуется.
