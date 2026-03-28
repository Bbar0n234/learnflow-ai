# Implementation Plan: feat-005 — E2E Scenarios + Polish

## Context

Все интеграционные итерации (feat-001…feat-004) завершены. Backend, Agent Runtime, Frontend и Docker full stack работают. Следующий шаг — прогон реальных пользовательских сценариев (UC-1, UC-2, UC-3) для обнаружения и фиксации интеграционных проблем. Цель — MVP «не стыдно показать».

### Референсы

- [workflow.md](doc/workflow.md) — жизненный цикл итерации
- [conventions.md](doc/tech/conventions.md) — ветки, коммиты, code quality
- [tasklist-integration.md](doc/tasks/tasklist-integration.md) — исходный таск-лист
- [use-cases.md](doc/product/use-cases.md) — UC-1/UC-2/UC-3
- [backend.md](doc/tech/backend.md) — API, SSE protocol, Service Layer
- [frontend.md](doc/tech/frontend.md) — компоненты, state management, SSE lifecycle
- [vision.md](doc/vision.md) — MVP-критерий «не стыдно показать»

### Решения архитектора

| Вопрос | Решение |
|--------|---------|
| Research skill | Не в scope. MCP Firecrawl достаточно |
| Known issues (cancel rollback, SSE-5/7) | Оба в бэклоге |
| Тестирование | Агент тестирует UC-1/UC-2/UC-3 (curl, Claude in Chrome). Деструктивные сценарии — архитектор вручную |
| Polish scope | Минимальный — только критичные UX-проблемы, обнаруженные при E2E |
| Модели | Основная: `z-ai/glm-5`, суммаризация: `z-ai/glm-4.7-flash` |

---

## Среда тестирования

**Всё E2E тестирование выполняется через Docker full stack**, а не через local dev server. Single-container pattern из feat-004: backend + frontend dist в одном контейнере, доступно по `http://localhost:8000`.

**Цикл при фиксах:** правка кода → `make docker-build && make docker-up` → ре-тест.

---

## Шаг 0: Setup

```bash
git fetch origin && git checkout -b feat/005-e2e-polish origin/develop
```

Ветка: `feat/005-e2e-polish` (согласно conventions.md: `<type>/<NNN>-<short-desc>`).

---

## Шаг 1: Обновление моделей

**Файл:** `configs/agent.yaml`

Изменения:
- `llm.model`: `"google/gemini-3-flash-preview"` → `"z-ai/glm-5"`
- `summarization.model`: `"google/gemini-3.1-flash-lite-preview"` → `"z-ai/glm-4.7-flash"`

Код LLM-клиента (`backend/app/infra/llm.py`) не меняется — модели подставляются через OpenRouter API.

**Проверка:**
```bash
make docker-build && make docker-up
curl http://localhost:8000/health  # {"status": "ok"}
```

**1a. Smoke test LLM:** Создать проект + чат → отправить простое сообщение → убедиться, что SSE-поток приходит с `text_chunk` от новой модели (`z-ai/glm-5`).

**1b. Smoke test MCP Firecrawl:** Отправить сообщение с просьбой найти что-то в интернете → убедиться, что `tool_start` для Firecrawl tools появляется в SSE-потоке. Если нет — проверить:
- `FIRECRAWL_API_KEY` проброшен в `.env` и доступен контейнеру
- Контейнер имеет доступ к внешней сети (`https://mcp.firecrawl.dev/v2/mcp`)
- Логи: `make docker-logs` — проверить наличие "Loaded N MCP tools" при старте

---

## Шаг 2: E2E — UC-1: Структурирование доклада

**Полный флоу:** создать проект → создать чат → описать тему → агент использует skill "structure" → итеративная доработка → артефакт.

### Тестирование агентом (curl + Claude in Chrome → Docker stack на `localhost:8000`)

**API-уровень (curl):**
1. `POST http://localhost:8000/api/projects` — создать проект
2. `POST http://localhost:8000/api/projects/{id}/chats` — создать чат
3. `POST http://localhost:8000/api/projects/{id}/chats/{cid}/messages` (SSE) — отправить запрос на структурирование доклада
4. Проверить SSE-поток: `text_chunk` (инкрементальный текст), `tool_start`/`tool_end` (для `load_skill`), возможно `artifact_created`, `done`
5. Отправить follow-up сообщение с доработкой → агент уточняет и создаёт артефакт
6. `GET /api/projects/{id}/artifacts` — проверить, что артефакт создан
7. `GET /api/projects/{id}/artifacts/{aid}` — проверить содержимое
8. `GET /api/projects/{id}/artifacts/{aid}/download?format=md` — проверить скачивание

**UI-уровень (Claude in Chrome → `http://localhost:8000`):**
1. Открыть приложение → AuthGate → ввести имя
2. Создать проект через sidebar → навигация в проект
3. Создать чат → описать тему
4. Проверить: текст стримится, tool indicator появляется при load_skill
5. Проверить: после done — полное сообщение загружено с сервера
6. Проверить: artifact card в чате, artifact в tab Artifacts

### Ожидаемые проверки

| Проверка | Способ |
|----------|--------|
| Агент подгружает skill "structure" | SSE: tool_start/tool_end для load_skill |
| Итеративная доработка | Второе сообщение → агент уточняет |
| Артефакт создаётся | SSE: artifact_created + GET /artifacts |
| Артефакт скачивается | GET /artifacts/{aid}/download?format=md |
| UI корректен | Claude in Chrome: визуальная проверка |

---

## Шаг 3: E2E — UC-2: Research по теме

**Полный флоу:** запрос на исследование → агент использует MCP tools (Firecrawl) для web search → структурированный результат со ссылками.

> **Примечание:** UC-2 тестируется как «agent + raw MCP tools (Firecrawl)», без dedicated research skill. Это упрощённая форма сценария из use-cases.md, где описан `load_skill("research")`. Решение архитектора: MCP tools достаточны для MVP. Research skill — отдельная задача вне feat-005, закрывающая пункт roadmap v1 «Базовый набор skills (structure, research)».

### Тестирование агентом (curl + Claude in Chrome → Docker stack на `localhost:8000`)

**API-уровень (curl):**
1. Создать проект + чат (или использовать существующие)
2. `POST http://localhost:8000/api/projects/{id}/chats/{cid}/messages` — запрос на исследование актуальной темы
3. Проверить SSE: `tool_start`/`tool_end` для Firecrawl tools (web search, scrape)
4. Проверить: ответ содержит ссылки на источники, структурирован

**UI-уровень (Claude in Chrome):**
1. Отправить research-запрос в чате
2. Проверить: tool indicators для MCP tools
3. Проверить: ответ с ссылками рендерится корректно (Markdown links)

### Ожидаемые проверки

| Проверка | Способ |
|----------|--------|
| Агент вызывает MCP tools | SSE: tool_start/tool_end для Firecrawl |
| Ответ содержит ссылки | Парсинг content на наличие URL |
| Ссылки кликабельны в UI | Claude in Chrome |

---

## Шаг 4: E2E — UC-3: Knowledge Sphere — персистентность контекста

**Полный флоу:** работа в проекте → агент обновляет KS → закрыть → вернуться → агент помнит контекст.

### Тестирование агентом (curl → Docker stack на `localhost:8000`)

1. Создать проект + чат
2. `POST http://localhost:8000/api/projects/{id}/chats/{cid}/messages` — содержательное сообщение (описание проекта, ключевые решения)
3. Проверить SSE: `tool_start`/`tool_end` для KS tools (`create_section`, `update_section`)
4. `GET http://localhost:8000/api/projects/{id}/sphere` — проверить, что KS содержит релевантные секции
5. Создать **новый чат** в том же проекте
6. `POST http://localhost:8000/api/projects/{id}/chats/{cid}/messages` — продолжить работу, ссылаясь на ранее обсуждённое
7. Проверить: агент знает контекст (ссылается на KS без повторного объяснения)

**UI-уровень (Claude in Chrome):**
1. Проверить tab Sphere — KS рендерится корректно
2. Проверить SphereEditor — можно редактировать и сохранять

### Ожидаемые проверки

| Проверка | Способ |
|----------|--------|
| Агент создаёт KS-секции | SSE: tool_start/tool_end для create_section |
| KS персистится | GET /sphere → content не пустой |
| Контекст сохраняется между чатами | Новый чат → агент помнит |
| Sphere UI работает | Claude in Chrome: просмотр + редактирование |

---

## Шаг 5: Фикс обнаруженных интеграционных проблем

Scope определяется результатами тестирования в шагах 2–4. Типичные категории:

- **Backend**: ошибки маппинга, некорректные SSE events, проблемы с KS tools
- **Frontend**: сломанный рендеринг, неработающая инвалидация, проблемы с навигацией
- **Agent**: агент не использует skill/tools когда должен, некачественные ответы

Каждый обнаруженный баг: зафиксировать → приоритизировать → фикс → `make docker-build && make docker-up` → ре-тест.

**Критические файлы (потенциально затронутые):**
- `backend/app/agent/runner.py` — SSE event processing
- `backend/app/agent/graph.py` — agent node, context engineering
- `backend/app/services/chat.py` — send_message orchestration
- `backend/app/agent/tools/*.py` — KS tools, artifacts, skills
- `frontend/src/features/chat/hooks/useAgentStream.ts` — SSE client
- `frontend/src/features/chat/components/ChatView.tsx` — chat rendering
- `frontend/src/features/chat/components/MessageItem.tsx` — message rendering
- `frontend/src/features/sphere/components/SphereView.tsx` — sphere UI
- `frontend/src/features/artifacts/components/ArtifactView.tsx` — artifact UI

---

## Шаг 6: Минимальный polish

Только критичные UX-проблемы, обнаруженные при E2E. Не трогать то, что работает.

**НЕ в scope:**
- Skeleton loaders, визуальный редизайн
- Улучшение empty states (текущие достаточны)
- Research skill
- Cancel HumanMessage rollback (backlog)
- SSE-5/SSE-7 верификация (архитектор вручную)

---

## Шаг 7: Тестирование архитектором (ручное)

**После завершения агентом шагов 1–6** (всё уже на Docker stack), архитектор проводит:

1. **Визуальная проверка UI** — общее впечатление «не стыдно показать» (через браузер на `http://localhost:8000`)
2. **SSE-5: ошибка LLM** — провоцирование ошибки (невалидный API key и т.д.)
3. **SSE-7: network drop** — `docker compose stop app` mid-stream, проверка UI graceful degradation
4. **Субъективная оценка** качества ответов агента с новыми моделями (z-ai/glm-5)

---

## Шаг 8: Документация

### Файлы

1. **`doc/tasks/iterations/integration/feat-005-e2e-polish/plan.md`** — этот план (скопировать из plan file)
2. **`doc/tasks/iterations/integration/feat-005-e2e-polish/summary.md`** — post-implementation summary:
   - Результаты E2E тестов (таблица PASS/FAIL)
   - Обнаруженные и исправленные проблемы
   - Known issues / отложенные проблемы
   - Затронутые файлы
3. **`doc/tasks/tasklist-integration.md`** — обновить статус feat-005 → ✅ Done
4. **`doc/product/roadmap.md`** — обновить статус v1 MVP если все пункты закрыты

---

## Шаг 9: Ревью архитектора

**Финальный шаг — дождаться ревью и обратной связи от архитектора перед коммитом и пушем.**

После одобрения:
```bash
git add <files>
git commit -m "feat(integration): E2E scenarios verification and polish for MVP readiness"
git push -u origin feat/005-e2e-polish
```
PR в develop.

---

## Инструменты (верификация актуальности)

Таблица «Быстро меняющиеся инструменты» из tasklist — Docker, Vite proxy, FastAPI CORS. Все три сконфигурированы и верифицированы в feat-004. Feat-005 не предполагает изменений в их конфигурации. Актуальные конфигурации:

| Инструмент | Конфиг | Статус |
|-----------|--------|--------|
| docker-compose | `docker-compose.yml` (v2 syntax: `docker compose`) | ✅ Verified feat-004 |
| Vite proxy | `frontend/vite.config.ts` → `/api` → localhost:8000 | ✅ Verified feat-004 |
| FastAPI CORS | `backend/app/main.py` → CORSMiddleware | ✅ Verified feat-004 |
