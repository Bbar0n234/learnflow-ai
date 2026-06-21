# Ф2b — INFRA · run-log

Замороженный тестовый фундамент feat-009. Один агент, keystone-фаза. По этому
фундаменту Ф3 (S1–S9) пишет тесты, инфру не трогает.

## Что построено

### Шов модели (C1)
- `backend/app/agent/graph_factory.py`: `GraphFactory.__init__` принимает
  `model_factory: ModelFactory | None = None`; в `build()` модель создаётся через
  `self._model_factory(settings, model_config)` вместо инлайнового
  `create_llm_from_config`. Дефолт = `create_llm_from_config` → прод не меняет
  поведения. `ModelFactory` — `Protocol` (без module-level состояния). Тесты
  переопределяют фабрику: `GraphFactory(..., model_factory=model_factory(fake))`.
- `build_graph(model=...)` и `LLMClassifier(llm=...)` уже инъектируемы — правок не
  потребовали.

### packages/testing (общий пакет, B5)
- Hatchling, flat layout, `learnflow_testing/` (как siem-contracts). Член
  workspace; dev-зависимость backend и siem-service; `py.typed`.
- `db.py` — testcontainers→URL (`make_urls`, per-worker имя через
  `PYTEST_XDIST_WORKER`), `create_database`, `run_migrations` (alembic upgrade
  head), `check_migration_drift` (`alembic check`), `transactional_session`
  (savepoint-rollback). `_alembic_config` нормализует относительный
  `script_location` (siem) к каталогу ini.
- `fakes.py` — `fake_chat_model` (GenericFakeChatModel), `ai_message`,
  `guard_classifier_model` / `garbage_classifier_model` / `raising_classifier_model`,
  `StubGuard` (вердикт + запись вызовов), `model_factory` (адаптер для C1).
- `factories.py` — `UserFactory`, `ProjectFactory` (async-factory-boy), `bind_session`.
- `sse.py` — `parse_sse`, `collect_sse`, `collect_event_stream`.
- `plugin.py` — pytest-плагин (entry point `pytest11`): кросс-проектная фикстура
  `postgres_container` (session). Через entry point, потому что per-package
  `--rootdir` ограничивает discovery conftest'ов — корневой conftest не грузится.

### Backend harness (`backend/tests/conftest.py`)
- `postgres_container`→`db_urls`(psycopg)→`_migrated_db`(create+upgrade head)→
  `engine`(session, NullPool)→`db_session`(function, transactional rollback,
  bind_session)→`current_user`→`app`(create_app + override get_db_session/
  get_current_user)→`client`(authed AsyncClient + ASGITransport).
- Изоляция loop: engine конструируется синхронно + `NullPool` → каждое
  `connect()` открывает соединение в loop теста; session-scoped engine
  совместим с function-scoped тестами без cross-loop reuse.

### Canary (smoke харнесса, НЕ S1–S9)
- backend: repository (real PG + rollback), handler (authed client → real PG),
  LLM/guard/factory seam (fake), drift guard (backend chain), smoke create_app.
- siem: drift guard (siem chain), smoke create_app.

### Frontend (Vitest/RTL/MSW)
- `frontend/vitest.config.ts` (jsdom, globals off), `src/test/setup.ts`
  (jest-dom + MSW lifecycle + `vi.mock("zustand")`), `src/test/test-utils.tsx`
  (`renderWithProviders`: свежий QueryClient, retry:false), `src/test/msw/`
  (server+handlers, заготовка SSE-мока), `__mocks__/zustand.ts` (сброс сторов в
  afterEach). Canary: `button.test.tsx` (RTL by role), `harness.canary.test.tsx`
  (component+useQuery+MSW).

### Makefile
- `test` — backend + siem (каждый exit 5 = OK, scoped к своему tests/).
- `test-cov` — backend branch-coverage + term-missing.
- `test-fe` — vitest run.
- `check`/`type-check` — mypy разбит на `backend/`, `services/siem-service/`,
  `tools/...` (single mypy-процесс не принимает два пакета с именем `tests`).

## Прогон в этом окружении
- Docker доступен → testcontainers поднимался реально.
- `make check` — зелено (ruff, mypy ×3, import-linter, arch-checker).
- `make check-fe` — зелено (tsc, eslint, prettier).
- `make test` — backend 10 passed, siem 2 passed (включая оба drift-guard'а и
  оба smoke на реальном Postgres).
- `make test-cov` — 10 passed, branch-coverage репорт.
- `make test-fe` — 2 passed.

## Решения / правки дрейфа
- Удалены `services/siem-service/alembic/__init__.py` и `.../versions/__init__.py`
  (docstring-only, не импортируются): siem-пакет `alembic` тенил установленный
  `alembic` (backend такого __init__ не имеет). Выравнивание раскладки с backend.
- Конфиг-правки (на ревью архитектора): mypy override
  `factory.*`/`async_factory_boy.*`/`testcontainers.*` = ignore_missing_imports
  (stubless test-libs, как существующие pdfkit/fuzzysearch); разбиение mypy в
  `make check`/`type-check`.
- Новых env-переменных НЕ вводил. Тестовые секреты (`JWT_SECRET`,
  `SIEM_JWT_SECRET`) выставляются `os.environ.setdefault` в conftest — не поля
  Settings, .env-примеры/compose не трогаются.

## Осталось для Ф3 / Ф5
- **Python 3.12**: дефолтный `python3` = 3.14 (pydantic-v1/langchain warning).
  Локальный `.venv` пересоздан на 3.12 (`uv venv --python 3.12`). На свежем
  окружении/CI закрепить интерпретатор (`.python-version` или uv-pin) —
  решение за архитектором.
- **Downgrade критичных ревизий** (upgrade→downgrade→upgrade) — паттерн из
  testing.md; заводится в Ф3 per-scope (S1/S8), не в фундаменте.
- CI-гейтинг (снять `continue-on-error`, `make test-fe` в `check-fe`) — Ф6.
