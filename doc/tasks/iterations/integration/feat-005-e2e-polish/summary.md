# Post-Implementation Summary: feat-005 — E2E Scenarios + Polish

## Результат

Все три use-case (UC-1, UC-2, UC-3) прошли E2E тестирование. Обнаружено и исправлено 5 интеграционных проблем + 1 UX polish. MVP соответствует критерию «не стыдно показать».

## E2E результаты

| Сценарий | API | UI | Статус |
|----------|-----|-----|--------|
| UC-1: Структурирование доклада | PASS | PASS | ✅ |
| — load_skill "structure" | tool_start/tool_end | — | ✅ |
| — Итеративная доработка | Агент отвечает с контекстом | — | ✅ |
| — Артефакт создаётся | artifact_created SSE + GET /artifacts | Artifact card + tab | ✅ |
| — Артефакт скачивается (md) | HTTP 200 (после фикса) | — | ✅ |
| UC-2: Research (Firecrawl) | PASS | — | ✅ |
| — firecrawl_search + scrape | tool_start/tool_end | — | ✅ |
| — Ответ со ссылками | URLs в ответе | — | ✅ |
| UC-3: Knowledge Sphere | PASS | PASS | ✅ |
| — create_section | tool_start/tool_end | — | ✅ |
| — KS персистится | GET /sphere → контент | Sphere tab | ✅ |
| — Контекст между чатами | Новый чат → агент помнит | — | ✅ |

## Обнаруженные и исправленные проблемы

### 1. Dockerfile: wkhtmltopdf недоступен в Debian Trixie

**Проблема:** `python:3.12-slim` обновился до Trixie, пакет `wkhtmltopdf` убран из репозиториев.
**Фикс:** Зафиксировать base image на `python:3.12-slim-bookworm`.
**Файл:** `Dockerfile:10`

### 2. Docker MTU: Firecrawl недоступен через VPN

**Проблема:** Docker Compose создаёт свою bridge-сеть с MTU 1500. При WireGuard VPN (MTU 1420) TLS handshake к `mcp.firecrawl.dev` зависает — пакеты слишком большие.
**Фикс:** Добавлен настраиваемый MTU через env var `${DOCKER_MTU:-1500}` в `docker-compose.yml`. Дефолт стандартный (1500), переопределение через `.env` (не коммитится). Это решение для локальной среды разработки, при Langfuse-миграции будет пересмотрено.
**Файл:** `docker-compose.yml:37-41`

### 3. Trailing slash: POST /api/projects возвращает 405

**Проблема:** SPA catch-all `@app.get("/{full_path:path}")` перехватывал `/api/projects` (без trailing slash) как GET-only path. FastAPI возвращал 405 вместо routing к POST-handler, зарегистрированному на `/api/projects/` (с slash).
**Фикс:** Заменить `"/"` на `""` в декораторах POST/GET projects router.
**Файл:** `backend/app/api/routes/projects.py:16,26`

### 4. Artifact download: UnicodeEncodeError на кириллическом заголовке

**Проблема:** `Content-Disposition` header содержал кириллический заголовок артефакта. HTTP headers допускают только latin-1, что вызывало 500.
**Фикс:** RFC 5987 `filename*=UTF-8''...` encoding для Content-Disposition.
**Файл:** `backend/app/api/routes/artifacts.py:58-76`

### 5. Artifact scroll: контент обрезается, не скроллится

**Проблема:** `ScrollArea` внутри `ArtifactView` не скроллился — flex-1 child без `min-height: 0` растягивался по контенту вместо ограничения высоты.
**Фикс:** Добавлен `min-h-0` на ScrollArea.
**Файл:** `frontend/src/features/artifacts/components/ArtifactView.tsx:66`

### 6. UX polish: неясный placeholder в ChatList

**Проблема:** Placeholder "Start a new chat..." создавал впечатление поля для сообщения, а не для заголовка чата.
**Фикс:** Изменён на "Chat title...".
**Файл:** `frontend/src/features/chat/components/ChatList.tsx:47`

## Отклонения от плана

- **Модели** обновлены согласно плану (`z-ai/glm-5`, `z-ai/glm-4.7-flash`)
- **Dockerfile и Docker MTU** — непредвиденные инфраструктурные проблемы, не описанные в плане
- **Trailing slash** — обнаружен при E2E, предсказуемо (SPA catch-all конфликт)
- **PDF export** — не тестировался (зависит от wkhtmltopdf, который работает в bookworm)
- **SphereEditor сохранение** — не тестировался агентом, верифицирован архитектором

## Known Issues / Бэклог

- **Cancel HumanMessage rollback** — при отмене user message остаётся в истории (бэклог)
- **SSE-5/SSE-7** — error handling и network drop верифицированы архитектором вручную
- **Research skill** — UC-2 покрывается MCP Firecrawl tools, dedicated skill — отдельная задача
- **Транзиентные пустые ответы модели** — один раз наблюдалось при E2E (load_skill отработал, но модель вернула пустой ответ). При повторе — штатно. Требует логирования для диагностики

## Затронутые файлы

```
configs/agent.yaml                                          # модели
Dockerfile                                                  # bookworm pin
docker-compose.yml                                          # MTU env var
backend/app/api/routes/projects.py                          # trailing slash fix
backend/app/api/routes/artifacts.py                         # Content-Disposition fix
frontend/src/features/artifacts/components/ArtifactView.tsx  # scroll fix
frontend/src/features/chat/components/ChatList.tsx           # placeholder fix
```
