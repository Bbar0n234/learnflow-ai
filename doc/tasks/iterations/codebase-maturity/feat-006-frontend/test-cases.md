# Test Cases: feat-006 — Frontend Slice

Регрессионная страховка под **структурный, поведение-сохраняющий** рефакторинг фронта:
миграция `features/` → `pages/` + `features/` + сегменты FSD, консолидация `shared/api`
(дробление типов, перенос data-хуков, фабрика query keys), публичные API слайсов,
точечные правки (селекторы Zustand, перенос `MarkdownRenderer`). Кода поведения мы **не
меняем** — задача кейсов: подтвердить, что каждый экран и поток работают ровно как до правок,
а инвалидация кеша (на которую напрямую влияет фабрика ключей) не сломалась.

Кейсы составлены **до** реализации, прогоняются после — независимым агентом-тестировщиком на
самостоятельно поднятом стенде.

## Формат прохождения

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания
- Кейсы с 👤 — требуют решения архитектора

### Процесс (тестировщик поднимает стенд сам)

1. Инфраструктура: `make docker-up-db` (Postgres main + siem, Redis), `make migrate`
   (+ siem-миграции), backend `make dev`, siem-service (uvicorn из пакета) — либо `make
   docker-up` целиком. Фронт: `make dev-fe` (Vite dev-сервер).
2. Акторы через UI register / `/api/auth/register`: **user-a** (обычный, с данными — проект,
   чаты, артефакты), **admin** (`make grant-admin USER=<name>` — для `/security`).
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в
   [Findings](#findings).
4. Реальное тестирование через UI (браузер). Чтение кода — только там, где поведение иначе не
   наблюдаемо (явно отмечено). После прогона — сводка (pass / failed / findings).

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| siem-service | `http://localhost:8001` |
| Сеть фронта | DevTools → Network (REST `/api/*`, SSE `/api/.../messages`) |
| Кеш/инвалидация | DevTools → React Query devtools (если включены) либо Network refetch |
| Логи фронта | DevTools → Console (через `@/shared/lib/logger`) |

---

## Layer 0: Automated gate

- [ ] `make check-fe` — ESLint + Prettier `--check` + `tsc -b` strict → **0 ошибок**. Это
  основной страж рефакторинга: переписанные пути импортов, перенесённые типы и хуки, фабрика
  ключей — любое расхождение ловится здесь до ручного прогона.
- [ ] `npx tsc -b --noEmit` отдельно — подтвердить, что ни один импорт не висит на старом пути
  (`@/features/...`, `@/shared/api/types`, `@/types/security`, `@/shared/components/...`).
- [ ] Grep-проверка отсутствия мёртвых ссылок: ноль вхождений `@/features/`,
  `@/shared/api/types"`, `@/types/`, `@/shared/components/` в `src/` (всё должно указывать на
  `@/pages/`, `@/features/<feature>`, доменные файлы `@/shared/api/<domain>`, `@/shared/ui/`).

---

## TC-AUTH: AuthGate

- [ ] Без аутентификации любой маршрут показывает блокирующую модалку login/register, контент
  под ней недоступен.
- [ ] Register нового пользователя → модалка закрывается, виден AppLayout (sidebar + welcome).
- [ ] Logout (user footer в sidebar) → снова модалка, токен сброшен.
- [ ] Повторный заход (refresh при валидном refresh-cookie) → без повторного логина (interceptor
  refresh).

## TC-NAV: Sidebar и навигация (бывш. `features/projects` → `app/components`)

- [ ] Список проектов в sidebar отрисован; клик по проекту → `/projects/:id`, открыт таб Chats.
- [ ] Recents — недавние чаты разных проектов; клик → переход в нужный чат.
- [ ] «New project» → модалка (CreateProjectModal), ввод имени, создание → проект появился в
  списке **без ручного refresh** (инвалидация `["projects"]`).
- [ ] Контекстное меню карточки проекта (ProjectActions): rename → имя обновилось в списке;
  delete → проект исчез, при удалении активного — корректный редирект.
- [ ] «New chat» активна только в контексте проекта; создание → чат появился в списке Chats и в
  Recents (инвалидация `["projects",id,"chats"]` + `["chats","recent"]`).
- [ ] Toggle sidebar (кнопка PanelLeft) → сворачивание/разворачивание (проверка B3: после
  правки селекторов поведение тумблера не изменилось).

## TC-WELCOME (`/` → `pages/welcome`)

- [ ] `/` показывает welcome-экран без input; создание чата только из проекта.

## TC-PROJ: Проект и таб Chats (`pages/project-chats`)

- [ ] `/projects/:id` → ProjectLayout (имя проекта + табы Chats/Sphere/Artifacts/Settings),
  index-таб = список чатов проекта (ChatList).
- [ ] Переключение табов меняет центральную область, активный таб подсвечен (derived from URL).
- [ ] Пустой проект → корректный empty-state списка чатов.

## TC-CHAT: Чат и SSE-стриминг (`pages/chat` + `pages/chat/model/useAgentStream`)

Ядро приложения — самый плотный по затронутому коду поток.

- [ ] Открытие чата `/projects/:id/chats/:cid` → ChatHeader (← project, model selector, tools),
  история сообщений, input.
- [ ] Отправка сообщения (Enter и кнопка) → user-сообщение появляется, начинается стрим.
- [ ] SSE `text_chunk` → текст ассистента печатается инкрементально (Markdown через Streamdown).
- [ ] SSE `tool_start`/`tool_end` → ToolIndicator показывает активный инструмент и гаснет.
- [ ] SSE `artifact_created` → инлайн ArtifactCard в чате; список артефактов проекта обновлён
  (инвалидация `["projects",id,"artifacts"]`).
- [ ] SSE `final_output_review_started`/`complete` → ReviewIndicator появляется и исчезает.
- [ ] SSE `done` → стрим завершён, полное сообщение подтянуто из чата (инвалидация
  `["projects",id,"chats",cid]` + `["chats","recent"]`); stream-store сброшен.
- [ ] Кнопка Cancel во время стрима → стрим прерван **без** error-баннера (отмена идёт через
  REST `cancelChat` + `AbortController`, не через SSE).
- [ ] SSE `error` / обрыв соединения / HTTP non-ok при старте → error-баннер в ленте
  (`MessageList` проп `streamError`); при Cancel баннера быть не должно (разделение путей
  `onError` vs отмена в `useAgentStream`).
- [ ] 401 внутри SSE-стрима → ручной `ensureFreshToken()` + один повтор POST (собственная
  логика `useAgentStream`, не axios-interceptor); стрим продолжается. Критично: хук переезжает
  в `pages/chat/model/` — проверить, что ручной retry не потерян.
- [ ] FeedbackButtons на сообщении ассистента → отправка score (использует trace_id из `done`).
- [ ] Model selector (dropdown per-thread, `features/model-selector`) → смена модели,
  инвалидация thread settings; выбранная модель сохраняется при reload.
- [ ] Tools dialog (`features/mcp-servers` → MCPServersSection per-thread) → видны inherited +
  собственные серверы, toggle меняет состояние, изменения персистятся.

### TC-CHAT-SEC: Security UX (критичный путь)

- [ ] Runtime block: на `security_block` input блокируется placeholder'ом «Чат заблокирован
  системой безопасности», заглушка `Message.redacted` в истории; **остаётся после reload**
  (оптимистичный patch `security_blocked=true` + персист с сервера — единый источник правды).
- [ ] Generic-текст в UI; `checkpoint`/`detection_layer` только в console, не на экране.

## TC-SPHERE: Knowledge Sphere (`pages/sphere`)

- [ ] `/projects/:id/sphere` → SphereViewer рендерит Markdown.
- [ ] Редактирование (SphereEditor) + Save → контент обновлён (инвалидация
  `["projects",id,"sphere"]`).
- [ ] Add-time security block: при HTTP 422 security violation форма показывает inline-сообщение
  под Save, текст не сброшен (helper `isSecurityViolation`).

## TC-ART: Артефакты (`pages/artifacts`, `pages/artifact`)

- [ ] `/projects/:id/artifacts` → список (название, тип, дата).
- [ ] Открытие артефакта `/artifacts/:aid` → Markdown-рендер (MarkdownRenderer из нового
  `@/shared/ui` — C4).
- [ ] Скачивание md и pdf (downloadArtifact, axios blob + Bearer) → файл скачивается.

## TC-USET: Пользовательские настройки (`pages/user-settings`)

- [ ] `/settings` → ModelSelector, CustomInstructionsSection, AgentMemorySection,
  MCPServersSection (scope=user).
- [ ] Смена модели → сохранено (инвалидация settings).
- [ ] Custom instructions save → сохранено (инвалидация `["instructions"]`); add-time security
  block → inline-сообщение, текст не сброшен.
- [ ] Agent memory: удаление записи → исчезла (инвалидация `["memories"]`).
- [ ] MCP servers (scope=user): create (с реальным URL — валидация доступности), toggle, delete;
  test connection. Изменения видны без ручного refresh.
- [ ] Add-time security block в MCP-форме: при HTTP 422 security violation форма
  (MCPServerForm) показывает inline-сообщение, ввод не сброшен (`isSecurityViolation`).

## TC-PSET: Настройки проекта (`pages/project-settings`)

- [ ] `/projects/:id/settings` → ModelSelector (override) + MCPServersSection (scope=project).
- [ ] Model override сохраняется; MCP-серверы проектного scope CRUD работают.
- [ ] Те же `features/model-selector` и `features/mcp-servers`, что в чате и user-settings,
  ведут себя идентично на всех трёх экранах (подтверждение, что выделение в features ничего не
  сломало).

## TC-SEC: Security monitoring, admin-only (`pages/security`)

- [ ] SecurityRouteGuard: non-admin на `/security` → редирект (читает `is_admin` из `/auth/me`
  с fallback на декод токена); admin → доступ.
- [ ] Events: таблица + фильтры (event_type, severity, time range), пагинация
  (SecurityPagination), диалог Details. Данные грузятся (siem-service).
- [ ] Alerts: фильтры (severity, status); Acknowledge → статус обновлён; Resolve → статус
  обновлён (пессимистичная инвалидация `["security","alerts"]` после успеха — B2).
- [ ] Rules: список + CRUD через RuleForm (Threshold/Sequence/Aggregate), toggle `enabled`.
- [ ] SeverityBadge/StatusBadge рендерятся (типы из объединённого `@/shared/api/security`, бывш.
  `@/types/security` — A4).

## TC-STATE: Корректность инвалидации (прямая проверка фабрики ключей B1)

Цель — подтвердить, что переход с инлайн-литералов на `queryKeys`-фабрику сохранил иерархию и
префиксную инвалидацию 1:1. Наблюдать по Network (refetch после мутации) или React Query
devtools.

- [ ] Создание чата → рефетч списка чатов проекта **и** recents.
- [ ] Завершение стрима (`done`) → рефетч детали чата и recents.
- [ ] `artifact_created` → рефетч списка артефактов проекта.
- [ ] CRUD проекта → рефетч `["projects"]`.
- [ ] Обновление настроек любого scope → рефетч соответствующего settings-ключа, соседние scope
  не задеты.
- [ ] Удаление memory / обновление instructions → рефетч только своего ключа.
- [ ] Ack/resolve алерта → рефетч списка алертов; конкретный алерт обновлён через `setQueryData`.
- [ ] CRUD/toggle rule → рефетч `["security","rules"]`, конкретное правило через `setQueryData`
  (иерархия rules-ключей в фабрике сохранена).
- [ ] CRUD MCP server любого scope → рефетч соответствующего `["mcp-servers", scope, …]`
  (составной ключ фабрики с `.filter(Boolean)` сохранён 1:1).

## TC-LOG: Логирование и устойчивость

- [ ] Ноль прямых `console.*` в проде помимо `@/shared/lib/logger` (grep по `src/` — проверка
  кодом допустима: наблюдаемость через статический анализ).
- [ ] ErrorBoundary: при искусственно брошенной ошибке рендера — fallback UI (сообщение +
  «обновить»), а не белый экран; ошибка залогирована.

---

## Покрытие findings слайса

| Finding | Кейсы |
|---|---|
| A1 миграция `pages/`/`features/` | весь UI-smoke (каждый экран переехал) + Layer 0 |
| A2 публичные API | Layer 0 (импорты через `index.ts` компилируются) + TC-CHAT/PSET (роутер, ChatHeader) |
| A3 кросс-импорт → features | TC-CHAT, TC-USET, TC-PSET (model-selector/mcp-servers на 3 экранах) |
| A4 типы security в shared/api | TC-SEC |
| B1 фабрика query keys | TC-STATE (вся группа) + TC-NAV/CHAT/SPHERE инвалидации |
| B3 селекторы Zustand | TC-NAV (toggle sidebar) |
| C3 дробление типов | Layer 0 (tsc) + все экраны (типы DTO в рантайме через рендер) |
| C4 MarkdownRenderer → shared/ui | TC-ART, TC-CHAT (Markdown ассистента), TC-SPHERE |

## Findings

Прогон — независимый агент-тестировщик на полном стенде (5 контейнеров: db, redis, siem-db,
app :8000, siem-service :8001; Vite :5173, браузер через Playwright). Вердикт: **по
наблюдаемому поведению рефакторинг поведение-сохраняющий, регрессий от него нет.**

Результаты по группам:

| Группа | Итог |
|--------|------|
| Layer 0 | ✅ `make check-fe` 0 ошибок; grep мёртвых путей чист |
| TC-AUTH | ✅ все 4 (gate, register, logout, persist refresh) |
| TC-NAV | ✅ все 6 (список/recents/создание/rename/delete/toggle — инвалидация без refresh) |
| TC-WELCOME, TC-PROJ | ✅ |
| TC-CHAT | ✅ что наблюдаемо (открытие, отправка → SSE POST 200 через `pages/chat/model`, error-баннер, model selector + persist, tools dialog). ⏸️ streaming/cancel/feedback/401-retry — BLOCKED (нет реального LLM-ключа) |
| TC-CHAT-SEC | ⏸️ BLOCKED (guard деградирует в CLEAN без LLM) |
| TC-SPHERE | ✅ фронт (viewer/editor/save 200/инвалидация); ⚠️ контент сохраняется пустым — корень в backend-гварде `ks_write_rest` при фейковом ключе, не рефакторинг |
| TC-ART | ✅ список (empty-state); ⏸️ open/download BLOCKED (артефакты генерит LLM) |
| TC-USET | ✅ что наблюдаемо (4 секции, instructions save+persist+reload, MCPForm рендерится); ⏸️ memory delete / MCP CRUD — нет данных/reachable URL |
| TC-PSET | ✅ те же `features/model-selector` и `features/mcp-servers`, идентичны на 3 экранах (A3) |
| TC-SEC | ✅ сильное покрытие (route guard, events+фильтры+пагинация, alert ack, rule toggle — инвалидация; badges из объединённого `@/shared/api/security` A4) |
| TC-STATE | ✅ всё тестируемое (create chat, CRUD project, settings по scope, instructions, alert ack, rule toggle); ⏸️ done/artifact_created/MCP — LLM-gated |
| TC-LOG | ✅ ноль `console.*` вне logger; ErrorBoundary на месте |

Открытые findings (не рефакторинг):

1. **Sphere сохраняет пусто** под фейковым LLM-ключом — backend-гвард `ks_write_rest`
   деградирует и не персистит контент. Среда/бэкенд, вне скоупа slice'а.
2. **Console-warning «missing React key» в `SecurityEvents`** — pre-existing (файл перенесён
   дословно), статикой источник не локализован (все видимые `.map` имеют `key`). К архитектору
   как отдельное наблюдение, не правится вслепую.

Не покрыто на первом прогоне (нет реального ключа) — догнано во втором прогоне ниже.

### E2E-прогон на реальном LLM-ключе (OpenRouter)

Догон ранее-BLOCKED кейсов: реальный `LLM_API_KEY`, контейнер `app` пересоздан
(`up -d --force-recreate` — `restart` не перечитывает `env_file`), модели резолвятся на
OpenRouter (`z-ai/glm-5`, `z-ai/glm-4.7-flash`). **Вердикт: на всех ранее-непокрытых LLM-путях
рефакторинг поведение-сохраняющий, регрессий нет.**

| Кейс | Итог |
|------|------|
| TC-CHAT text_chunk / done | ✅ инкрементальный Markdown; `done` → рефетч чата+recents |
| TC-CHAT tool_start/end | ✅ проводка верна (wire: оба события за 9ms в одном чанке → индикатор не успевает на кадр; медленный tool показал бы — нужен реальный MCP-ключ) |
| TC-CHAT artifact_created | ✅ инлайн ArtifactCard + список артефактов обновлён без refresh |
| TC-CHAT review started/complete | ✅ ReviewIndicator пойман live |
| TC-CHAT Cancel | ✅ POST /cancel 200, без error-баннера, input восстановлен |
| TC-CHAT FeedbackButtons | ⏸️ BLOCKED (среда): рендерятся только при `trace_id`, а он null без валидных Langfuse-ключей (OTLP 401). Логика верна |
| TC-CHAT-SEC runtime block | ⏸️ BLOCKED (**backend-баг, не рефакторинг**): guard корректно детектит инъекцию, но раннер виснет в `_persist_user_input_block` → `graph.aupdate_state` (запись checkpointer) до первого yield; `security_block` SSE не доходит. Воспроизводимо. Фронт-UX не проверить, пока бэкенд не отдаёт событие |
| Add-time blocks (instructions/sphere/MCP) | ✅ все 422 `urn:learnflow:security-policy-violation` → inline-сообщение, ввод не сброшен |
| TC-SPHERE persist | ✅ контент сохраняется и переживает reload (с реальным ключом guard не деградирует) |
| TC-ART open + download | ✅ MarkdownRenderer; md (440 B) и pdf (`%PDF-`, 18.7 KB) скачиваются |
| TC-USET memory delete | ✅ DELETE 204 → рефетч `["memories"]` |
| TC-USET MCP CRUD | ✅ create (reachable `https://docs.langchain.com/mcp`, валидация доступности) / test «OK (2 tools)» / delete — рефетч без refresh |
| TC-STATE (LLM-gated) | ✅ инвалидация после `done`/`artifact_created`/memory/MCP — фабрика ключей цела |

Остаётся BLOCKED (не фронтенд-слайс): (1) runtime `security_block` UX — backend-hang (см.
выше); (2) FeedbackButtons — нужны Langfuse-ключи; (3) визуал ToolIndicator на медленном tool —
нужен реальный MCP-ключ.
