# feat-009 · План реализации

Исполняемый план итерации. Опирается на `decisions-phase1.md` (решения) и `theory/` (обоснования).
Ведём кастомным фазовым workflow (не стандартный конвейер оркестратора). Этот документ — источник
правды по исполнению; переживает сжатие контекста.

## Принципы исполнения (из разбора с архитектором)

- **Convention-first.** Сначала формализуем тест-конвенции + чек-листы ревью, и только по ним пишем тесты.
- **Single source of truth.** Промпты тестировщика/ревьюера/фиксера **ссылаются** на `conventions.md`, не
  дублируют его содержимое. Никакого копирования норм в промпты/скиллы.
- **Параллелим по полным непересекающимся скоупам.** Скоуп не рвём между агентами; берём так, чтобы и
  по коду без конфликтов (разные директории), и логически цельно (сервис не пилится на двух агентов).
- **Journaling (версионируемый дрибл контекста).** Каждый агент пишет run-log в свой документ: ревьюер
  фиксирует findings → фиксер читает, чинит, дописывает примечания. Инсайты/ошибки/шаги не умирают в
  памяти агента. Формат — на базе run-log из feat-008 (норма ре-верификации), без дублирования.
- **Все агенты — на Opus.** Токены не экономим, приоритет — качество и скорость.
- **Ревью на каждом ключевом шаге.** Ревьюятся и сами конвенции (полнота/ясность), и написанные тесты.
- **Test-integrity guardrails (A6).** Имплементер не трогает тест-файлы; автор тестов независим от автора
  кода; git/make-страж неизменности тестов; лёгкое человеческое ревью. Детали — `theory/06-tdd.md`.

## Фазы

### Ф2a — CONVENTIONS (convention-first) · [gate архитектора]
Пишем раздел тестов в `conventions.md` (per-domain дробление по образцу feat-008) + чек-листы для
ролей tester/reviewer. Содержимое — синтез теории и решений: модели и слои (что тестируем/чем),
sociable+fakes, дубли, тестовая БД (testcontainers + migrations + transaction-rollback + per-worker
под xdist), async (pytest-asyncio auto), HTTP (ASGI-клиент + auth-фикстура), фейки LLM/guard, граница
unit/eval, антипаттерны, DoD через поведение, A6-guardrails. **Ревью полноты** отдельным агентом.
Выход: конвенции + чек-листы. Гейт архитектора.

### Ф2b — INFRA (один агент, замораживается) · [gate]
Строит и фиксирует общий фундамент:
- **Шов модели** — model-factory в `GraphFactory` (C1, вариант а), переопределяемая в тестах.
- **conftest-иерархия** + scope-политика (session: контейнер/engine/миграции; function: соединение/
  транзакция/клиент).
- **Тестовая БД** — testcontainers Postgres, `alembic upgrade head`, transaction-rollback на тест,
  per-worker DB под xdist; страж autogenerate-дрейфа на обе alembic-цепочки.
- **Фикстуры** — async, аутентифицированный клиент (override `Depends`), фабрики (factory_boy + async).
- **Фейки LLM/guard** — `GenericFakeChatModel` / стаб-guard, возвращающий `Verdict`.
- **SSE-хелперы**, **smoke-boot** (`create_app()` обоих сервисов).
- **`packages/testing`** — общий пакет тест-утилит (B5).
- **Frontend** — Vitest/RTL/MSW setup (jsdom, без браузера).
- **Makefile** — `test` / `test-fe` / `test-cov`; CI-проводка (гейтинг F3 — позже, Ф6).
Гейт архитектора → заморозка. После заморозки инфру в Ф3 не трогаем.

### Ф3 — COVERAGE (fan-out, Opus, journaling)
Партиция по скоупам (ниже). Каждый агент пишет тесты своего скоупа против конвенций + замороженной
инфры; ведёт run-log. Архивные наборы feat-004/005/007 вливаются в общую рамку в своих скоупах.

### Ф4 — REVIEW (fan-out, Opus)
Ревьюеры проверяют тесты против конвенций и чек-листов (поведение-не-реализация, нет false-green/
флака, фикстуры, нейминг, A6); findings → run-log; имплементеры/фиксеры правят (loop ≤2). Автор
ревью независим от автора тестов.

### Ф5 — GREEN (Opus, journaling)
Прогон всего `make test`/`make test-fe`; доводим до зелёного. Очевидные баги, вскрытые тестами, чинят
**отдельные** фикс-агенты (журналируют), не имплементеры тестов. Coverage-репорт. Гейт архитектора.

### Ф6 — WORKFLOW
Встраиваем роли tester/reviewer/fixer + норму journaling + A6-guardrails в `aidd-orchestrator` (FSM,
промпты в `.claude/skills/aidd-orchestrator/prompts/`), single-source-of-truth (ссылки на conventions,
не дубль). Снимаем `continue-on-error` в CI — тесты в гейт (F3). Гейт архитектора.

## Партиция скоупов Ф3 — вертикальная нарезка по подсистемам

Решение архитектора: режем **вертикально** (подсистема end-to-end: route → service → repository →
model + её тесты), а не горизонтально по слоям. Сервис не пилится между агентами; директории тестов
(`tests/<scope>/`) не пересекаются. Cross-cutting (страж дрейфа миграций, `packages/testing`, conftest,
фейки) живёт в Ф2b-инфре, не в скоупах Ф3.

| Скоуп | Подсистема (end-to-end) | Ключевые модули | Бар |
|-------|-------------------------|-----------------|-----|
| S1 Auth & access | JWT/refresh/ротация, rate limit, шифрование | `routes/auth`, `services/auth`+`encryption`, `repos/refresh_token`+`user`, `models/user`+`refresh_token`, `api/deps`, `security_pipeline` | критпуть — глубина |
| S2 Agent guard | prompt-injection guard, ветвление по вердикту | `agent/security/*` (classifier, guard, canary, corpus, detectors, observer, types), `agent/runtime_security` | критпуть — глубина |
| S3 Agent runtime | граф/ноды/edges, SSE-маппер, checkpointer — на fake LLM | `agent/graph`, `graph_factory`, `runner`, `prompt_builder`, `error_mapper`, `stream_events`, `checkpoint_history`, `config`, `tracing` | критпуть — глубина |
| S4 Projects & artifacts | основной REST-спайн продукта | `routes/projects`+`artifacts`, `services/project`+`artifact`, `repos/project`+`artifact`+`thread_view`, `models` | happy + ошибки |
| S5 Chat & streaming | чат, сообщения, SSE-оркестрация, feedback | `routes/chats`+`messages`+`feedback`, `services/chat`+`agent_runner` | критпуть (SSE) — глубина |
| S6 Knowledge sphere | sphere REST + agent-tool + fuzzy patch | `routes/sphere`, `services/sphere`, `agent/tools/knowledge_sphere`+`ks_helpers`+`store_helpers` | happy + ошибки |
| S7 Memory · settings · MCP · models | персонализация + конфиг интеграций | `routes/user_memory`+`settings`+`mcp_servers`+`models`, `services/user_memory`+`model_config_resolver`+`mcp_server`+`mcp_tool_resolver`+`url_validator`, `repos/settings`+`mcp_server`, `agent/tools/user_memory`+`skills`, `agent/skills` | happy + ошибки |
| S8 SIEM + contracts | siem-логика + страж дрейфа контракта | `services/siem-service`, `packages/siem-contracts`, `repos/trace_store` | unit + contract |
| S9 Frontend | хуки/сторы/компоненты на Vitest/RTL/MSW (+SSE-мок) | `frontend/src` — features, stores, pages, shared | unit + integration |

9 агентов в веере, директории не пересекаются.

## Решения архитектора по форкам (закрыты)

1. **F1 — глубина.** Широкое покрытие всех скоупов на уровне поведения (happy + основные ошибки/
   авторизация) **+ глубина на критпутях**: S1/S2/S3/S5 дополнительно получают edge/negative-кейсы.
   Бар на скоуп см. в колонке таблицы.
2. **Партиция — вертикальная** (S1–S9 выше). Требует финального подтверждения архитектора (нужна
   только к Ф3; Ф2a/Ф2b от неё не зависят).
3. **A3/A4 — диагностика + ratchet, без числа.** Мерим branch-coverage, репортим, фиксируем правило
   «не понижать». Жёсткого числового floor не ставим, пока база ~0%. DoD — через поведение, не процент.
4. **Journaling — `runlog/<scope>.md`** в директории итерации, по образцу run-log feat-008. Ревьюер
   дописывает findings, фиксер — примечания. Параллельные агенты не конфликтуют (разные файлы).

## Зафиксированные решения (см. `decisions-phase1.md`)

B1 pytest-asyncio `auto` · B2 testcontainers · B3 миграции (`upgrade head` + downgrade критичных + 2
цепочки) · B4 transaction-rollback + per-worker DB · B5 `packages/testing` · C1 model-factory в
`GraphFactory` · C2 VCR точечно · C4 evals → backlog · A5 ручные test-cases (узко) · A6 TDD-стойка +
guardrails · E1 скиллы skip · frontend Vitest (Playwright e2e → backlog).
