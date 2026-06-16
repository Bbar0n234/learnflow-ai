# Summary: feat-006 — Frontend Slice

Slice-аудит фронтенда против skill `feature-sliced-design` + общих паттернов чистого кода, с
последующей миграцией на каноничный FSD и консолидацией слоя данных. Аудит шире скилла: ось
состояния (Zustand + TanStack Query) закрыта конвенцией (ядро отклонённого
`react-state-management`).

## Что сделано

**Структура — миграция на канон FSD.** Бывший `features/` (де-факто экраны маршрутов) разнесён
по слоям:
- `pages/` — 9 слайсов уровня маршрута с сегментами `ui/` (и `model/` для `pages/chat` —
  `useAgentStream`), публичный API в `index.ts` каждого слайса.
- `features/` — только реально переиспользуемое между страницами: `model-selector`,
  `mcp-servers` (тянут chat + user-settings + project-settings). Этим растворён кросс-импорт
  одного слоя (A3): страницы тянут общие куски вниз, из `features/`.
- `app/components/` — постоянный Sidebar + управление проектами (project CRUD-виджеты), shell.
- Слои `widgets/`/`entities/` не вводились (нет материала).

**shared/api — консолидация.** Монолит `types.ts` (199 строк) и `types/security.ts` разнесены
по доменным файлам; в каждом домене — типы + API-функции + TanStack Query data-хуки (CRUD —
инфраструктура, по FSD место в `shared/api`). Новые `query-keys.ts` (фабрика B1),
`pagination.ts` (`ListResponse`), `sse.ts` (`SSEEvent`).

**Фабрика query keys (B1).** Все ~20 хуков и точки инвалидации переведены с инлайн-литералов на
единый `queryKeys`-объект. Иерархия ключей сохранена 1:1 — префиксная инвалидация работает как
раньше. Это главный анти-регрессионный выигрыш slice'а (опечатка в ключе → молчаливо несработавшая
инвалидация).

**Точечное.** B3: `AppLayout` переведён на селекторы Zustand. C4: `MarkdownRenderer` →
`shared/ui`, каталог `shared/components` удалён; граница «shadcn / наше» — соглашением. C1:
удалён мёртвый питоновский `features/security/__init__.ts`.

**Публичные API (A2).** `index.ts` на каждый `pages/`/`features/` слайс; роутер/layouts/Sidebar/
ChatHeader/settings-страницы импортируют через них. `shared/` — по доменным файлам без баррелов
(осознанное решение: у shared нет слайсов).

## Конвенции и доки

- `conventions.md` — новый § Frontend (только проектные решения: FSD-адаптация и осознанные
  отступления, ось состояния, фабрика ключей, optimistic vs пессимистик B2, селекторы, граница
  shadcn). Содержимое скилла не дублируется.
- `frontend.md` — переписаны § Module Structure (дерево + Mermaid-диаграмма под `pages/`/
  `features/`), § API-модули и хуки, исправлен дрейф таблицы query keys (D1: декларировались
  `["user", …]`-ключи, которых в коде нет; приведено к фактическим + ссылка на фабрику).

## Развилки (решены архитектором)

- **pages vs features-as-sections** → миграция на `pages/` сейчас (не откладывать: позже, в фазе
  активного шипинга фич, на структурный рефакторинг не будет окна).
- **Публичные API** → делаем на слайсы независимо от структуры.
- **Кросс-импорт ChatHeader** → растворён выделением `features/` (Strategy C/D не понадобилась).
- **Data-хуки** → в `shared/api/<domain>`; страница-специфичная оркестрация (`useAgentStream`) —
  в `pages/chat/model`.
- **Типы** → дроблены по доменам в `shared/api`.
- **shadcn vs наше** → слить в `shared/ui`, граница соглашением (вариант 2).

## Верификация

- `make check-fe` (ESLint + Prettier + tsc strict) — 0 ошибок.
- Документ тест-кейсов составлен до правок, прошёл ревью полноты (независимый субагент: 2
  обязательных пробела закрыты — SSE `error`, add-time block в MCP-форме).
- Прогон — независимый агент-тестировщик на полном стенде (Playwright, 5 контейнеров), **два
  захода**: без ключа (не-LLM пути) и на реальном OpenRouter-ключе (LLM-gated пути). Вердикт обоих:
  **поведение-сохраняющий, регрессий от рефакторинга нет** — стриминг (text/tool/artifact/review/
  done/cancel), инвалидация кеша, add-time security blocks, MarkdownRenderer, model-selector/
  mcp-servers подтверждены вживую. Детали — в [test-cases.md](test-cases.md#findings).

## Хвосты (не рефакторинг)

1. **Backend-баг (security-критичный, surfaced при E2E):** runtime `security_block` — раннер
   виснет в `_persist_user_input_block` → `graph.aupdate_state` (запись checkpointer) после
   детекции инъекции, SSE-событие не доходит. Воспроизводимо. Путь раньше не отрабатывал (без LLM
   guard деградировал в CLEAN). Не фронтенд-слайс — отдельный backend/agent fix, эскалирован
   архитектору.
2. Console-warning «missing React key» в `SecurityEvents` — pre-existing, источник статикой не
   локализован; не правился вслепую (решение архитектора — пропустить).
3. Среда (не блокеры рефакторинга): FeedbackButtons требуют валидных Langfuse-ключей (trace_id);
   визуал ToolIndicator на медленном tool — реального MCP-ключа.
4. Тестируемость LLM-guard путей без живого провайдера — записано в feat-009 (см.
   tasklist-codebase-maturity § feat-009 «Контекст из slice-аудитов»).
