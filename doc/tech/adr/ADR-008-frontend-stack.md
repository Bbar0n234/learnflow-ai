# ADR-008: Frontend Stack

## Статус

Принято

## Контекст

LearnFlowAI — chat-first SPA для работы с AI-агентом. Ключевые требования к фронтенду:
- SSE-стриминг ответов агента с рендерингом Markdown (включая code blocks)
- CRUD проектов, чатов, артефактов через REST API
- Knowledge Sphere viewer/editor
- Архитектурная гибкость для расширения без переписывания
- AIDD: код генерируется LLM-агентом — стек должен быть хорошо представлен в training data

## Решения

### Сборка: Vite

Индустриальный стандарт для React SPA после deprecation CRA. ~60M npm/нед, ~78K stars. Быстрый dev-server, HMR, минимальная конфигурация. Upgrade path на Rolldown (Rust-движок) в Vite 8.

**Отклонено:** Next.js — SSR/SEO не нужны для приватного чат-интерфейса, лишняя сложность.

### UI: shadcn/ui + Tailwind CSS v4

shadcn/ui (~106K stars) — компоненты копируются в проект (не зависимость), полный контроль, zero runtime overhead. Построен на Radix UI (доступность). Tailwind v4 — Rust-движок, CSS-first конфиг. Проект с нуля — стартуем сразу на v4.

**Отклонено:** MUI, Ant Design — тяжёлые, CSS-in-JS runtime, сложная кастомизация. Chakra UI — менее активная экосистема. Mantine — своя система стилей, не Tailwind.

**Риски:** shadcn зависит от Radix UI (maintenance risk), нет автообновлений. Для проекта одного разработчика — приемлемо.

### State: TanStack Query v5 + Zustand v5

TanStack Query (~12M npm/нед, ~48K stars) — серверный state: кеширование, рефетч, loading/error states. Zustand (~24M npm/нед, ~57K stars) — UI state: sidebar, тема, локальные флаги.

Правило разделения: серверные данные живут только в TanStack Query, Zustand — только для client-only state. Дублирование запрещено.

**Отклонено:** Redux Toolkit — boilerplate. SWR — беднее функционал, нет DevTools. Jotai — для сложного взаимозависимого state (не наш случай).

### HTTP-клиент: axios (REST) + fetch (SSE)

Два транспорта — два инструмента. axios (~80M npm/нед, ~108K stars) для REST: interceptors, автоматический JSON, throw на не-2xx, максимальное качество LLM-генерации. SSE-стриминг через native fetch + ReadableStream — axios спроектирован под "запрос → полный ответ" и не поддерживает инкрементальное чтение потока.

**Отклонено:** ky — LLM генерируют хуже, клонирует responses в hooks (проблема для стриминга). wretch, ofetch — LLM генерируют плохо, маленькое community. Голый fetch для REST — verbose boilerplate на каждый вызов (проверка response.ok, ручной .json(), headers).

### Роутинг: React Router v7 (library mode)

~20M npm/нед, ~56K stars. Library mode = проверенные v6-паттерны, максимальная LLM-reliability. ~6 маршрутов — type-safe routing не критичен.

**Отклонено:** React Router v7 framework mode — тянет file-based routing и Vite-плагин, избыточно для SPA. TanStack Router — type-safe, но меньше community (~1.9M npm/нед) и LLM training data; миграция возможна при необходимости.

### Markdown/стриминг: Streamdown

Создан Vercel специально для AI-чатов (~4.4K stars, v2.2). Инкрементальный парсинг (не перепарсивает всё на каждый токен), graceful handling незакрытого Markdown mid-stream, встроенный Shiki (подсветка кода как в VS Code). Drop-in замена react-markdown по API.

**Отклонено:** react-markdown — перепарсивает весь документ на каждый токен, ломается на неполном Markdown при стриминге, требует кастомной мемоизации. marked/markdown-it — HTML output, нужен `dangerouslySetInnerHTML`.

### Иконки: Lucide React

Дефолт shadcn/ui, tree-shakeable, лёгкие.

### Линтинг: ESLint + Prettier

Стандарт для TypeScript/React.

## Следствия

- TypeScript strict mode с первого дня
- Весь стек — mainstream, хорошо документирован, AI-friendly для AIDD
- При росте сложности маршрутов — возможна миграция на TanStack Router
- Streamdown привязывает к Vercel-экосистеме для Markdown-рендеринга, но API совместим с react-markdown (обратная миграция проста)
