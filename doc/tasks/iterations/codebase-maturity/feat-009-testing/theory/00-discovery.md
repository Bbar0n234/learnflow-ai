# feat-009 · Discovery: текущее состояние тестов + вывод по скиллам

Стартовая карта итерации: что у нас сейчас есть по тестам и есть ли что взять из готовых скиллов. Опирается на две разведки — инвентаризацию репозитория и discovery скиллов по тестированию.

---

## Часть 1. Текущее состояние — чистый лист

Главный факт: **живой тестовой инфраструктуры в репозитории нет.** Запускаемых тестов ноль, тест-зависимостей нет, CI тесты не гейтит. Весь когда-либо написанный код тестов лежит «заархивированным» внутри артефактов прошлых итераций и намеренно выведен из коллекции pytest.

### Что есть (точнее — чего нет)

- **Запускаемых тестов — ноль.** `backend/tests/` содержит только пустой `__init__.py`. У `services/siem-service/` каталога `tests/` нет вовсе (хотя `pyproject.toml` объявляет `testpaths=["tests"]`). Фронтенд тестов не имеет совсем.
- **Тест-зависимостей нет** кроме голого `pytest>=9.0` в корневой dev-группе. Отсутствуют полностью (проверено grep'ом по всем `pyproject.toml`): `pytest-asyncio` (хотя async-код повсюду), `pytest-cov`, `pytest-mock`, `factory-boy`, `faker`, `testcontainers`. `httpx` и `anyio` есть, но как **runtime**-зависимости backend, не тестовые.
- **Живого `conftest.py` и фикстур нет.** Единственный `conftest.py` в репозитории — внутри архива feat-007 (только манипуляция `sys.path`, без фикстур). Фабрик (`factory-boy`/`Faker`) в исходниках нет.
- **Тестовой БД-инфраструктуры нет:** ни отдельной test-базы, ни testcontainers, ни транзакционного отката, ни session-фикстур SQLAlchemy.
- **CI тесты не гейтит.** В `.github/workflows/ci.yml` job `check` гоняет `make check` / `make check-fe` (ruff + mypy + lint-imports + arch_checker + tsc + eslint + prettier) и сборку. Шаг `make test` присутствует, но помечен `continue-on-error: true`, а `make test` сейчас собирает 0 тестов (exit 5 → трактуется как успех). То есть тесты не блокируют мерж ничем.
- **Smoke на `create_app()` в коллекции нет.** `create_app()` определён в обоих сервисах (`backend/app/main.py:509`, `services/siem-service/siem_service/main.py:109`), `/health` есть в обоих. Реально оба приложения инстанцирует только архивный `test_cors_on_500.py` (через `TestClient` без lifespan) — но он не подхватывается коллекцией.

### Заархивированные наборы (материал для вливания в общую рамку)

| Итерация | Путь | Объём | Что тестирует | Стек / долг |
|----------|------|-------|---------------|-------------|
| feat-004 | `doc/tasks/iterations/codebase-maturity/feat-004-fastapi/archived-point-tests/` | ~17 | argon2 hash/verify, refresh-токены, `RateLimiter` (лимит/окно/retry_after), CSV-парсинг `CORS_ORIGINS`, StrEnum-регрессии `agent.security.types` | Голый pytest, синхронные функции, **без фикстур и conftest**, прямые импорты `app.*` |
| feat-005 | `doc/tasks/iterations/codebase-maturity/feat-005-agent-runtime/archived-point-tests/` | 46 | llm-фабрики, ModelConfigResolver, user_memory tools, stream event mapper, run tracer, checkpoint history, **критпуть RuntimeSecurityEnforcer (4 чекпоинта)**, langfuse init | pytest; **async через `asyncio.run()` вручную — без `pytest-asyncio`**; фикстур нет, вместо них **дублирующиеся ручные фейки `_FakeGuard`/`_FakeGraph`/`_FakeCheckpointer`** между файлами (README прямо отмечает как долг для feat-009) |
| feat-007 | `doc/tasks/iterations/codebase-maturity/feat-007-cross-cutting/tests/` | 5 | CORS-заголовок на 500 (оба `create_app()`), guard degradation, `handle_tool_errors` в ToolNode, SIEM `is_transient_db_error` | **Префикс `test_` сохранён + реальный conftest** (sys.path → `backend/`); `unittest.mock`, langgraph `InMemorySaver`, `structlog.testing.capture_logs`; рассчитаны на ручной запуск |

Файлы feat-004/005 переименованы в `*_tests.py` (без префикса `test_`), чтобы pytest их не подбирал.

### Пробелы (чего нет вообще)

1. Ни одного запускаемого теста.
2. Тест-зависимостей нет кроме `pytest>=9.0` (нет `pytest-asyncio`, `pytest-cov`, `pytest-mock`, `factory-boy`, `faker`, `testcontainers`, httpx-as-test-dep).
3. Живого `conftest.py` и фикстур/фабрик нет.
4. Тестовой БД-инфраструктуры нет (test-database, testcontainers, транзакционный откат, session-фикстуры).
5. Async-стратегия не принята: архивы используют `asyncio.run()` вручную, решение про `pytest-asyncio` (`asyncio_mode`) не принято.
6. Smoke/health-теста на `create_app()` в коллекции нет ни для backend, ни для siem.
7. CI не гейтит тесты: `make test` с `continue-on-error: true`, coverage-порога нет.
8. Frontend без тестов целиком: нет vitest/testing-library/playwright, конфигов и `test`-скрипта.
9. Дублирование ручных фейков между архивными файлами — нет общих фабрик/фикстур.
10. Нет Makefile-целей `test-fe`, `test-cov`/coverage, `test-siem` — только backend-only `test`.

### Вывод части 1

**Фаза 2 (инфраструктура) строится практически с нуля — легаси-инфры, которую надо тащить и не сломать, нет.** Это упрощает решения: мы не мигрируем существующий тестовый фундамент, а проектируем его сразу под актуальные практики. Архивные наборы — не инфраструктура, а отдельные тест-кейсы, которые после постройки фундамента переписываются под общие фикстуры (особенно критпуть RuntimeSecurityEnforcer из feat-005, который надо сохранить).

---

## Часть 2. Skill discovery — вывод

Готового drop-in скилла, который закрыл бы все три оси тестирования проекта (async-pytest backend + Vitest/React frontend + evals LangGraph-агента), **не существует.** По осям:

- **Backend (pytest-async / FastAPI / LangGraph / asyncpg):** прямого качественного скилла нет. Ближайшие — `wdm0006/testing-python-libraries` (но library-oriented: tox/coverage-матрицы, а не async-приложение) и `manikosto` (навязывает strict-OOP тест-классы + обязательный Allure — **конфликт с конвенциями проекта**). Годятся только как reference-материал, не как зависимость.
- **Frontend (React / Vitest):** предложение сильнее. Официальный `webapp-testing` (Playwright UI-верификация) и `citypaul/.dotfiles` (Vitest **Browser Mode** + vitest-browser-react, mutation-testing — современный стек). Реальные кандидаты «адаптировать», но **сверить с уже подключённым Playwright MCP**, чтобы не плодить дубль.
- **LLM/agent-evals (главная специфика проекта):** **дыра.** Качественного скилла под Langfuse-evals LangGraph-агента нет; всё живое в нише (`langchain-ai/langsmith-skills`) завязано на **LangSmith**, а проект на **Langfuse**. `langchain-ai/langchain-skills` — про фреймворки, не про тесты.
- **Язык-агностичная дисциплина:** `obra/superpowers` (test-driven-development, RED-GREEN-REFACTOR, «Iron Law») и часть `citypaul` (`test-design-reviewer`, `finding-seams`, `characterisation-tests`, `mutation-testing`) — хорошая концептуальная база для нашего собственного слайса.

### Таблица кандидатов

| Скилл / коллекция | Источник | Покрывает | Рекомендация |
|-------------------|----------|-----------|--------------|
| **webapp-testing** | `anthropics/skills` (official) | Playwright UI-верификация локальных веб-приложений | **Изучить / брать точечно** — сверить с нашим Playwright MCP на дубль |
| **test-driven-development** | `obra/superpowers` | Дисциплина RED-GREEN-REFACTOR, антипаттерны; язык-агностично | **Изучить** как reference, не «как есть» (жёсткий/опинионированный) |
| **citypaul testing-suite** (react-testing, finding-seams, test-design-reviewer, mutation-testing, characterisation-tests) | `citypaul/.dotfiles` | Самая богатая связка: TDD, React (Vitest Browser Mode), мутационное, ревью тест-дизайна, поиск «швов» | **Брать для фронта / майнить язык-агностичное**; вендорить и адаптировать |
| **testing-python-libraries** | `wdm0006/python-skills` | pytest: фикстуры, параметризация, Hypothesis, coverage, tox | **Изучить** — ближайшее к backend-pytest, но library-oriented (частичный фит) |
| **python-testing / pytest-oop-patterns / api-testing-patterns** | `manikosto/claude-code-python-stack` | pytest, httpx AsyncClient, Allure, strict-OOP | **Не брать as-is** (Allure/OOP конфликт); вынуть только httpx-AsyncClient-паттерны |
| **langsmith-skills** | `langchain-ai/langsmith-skills` | observe/evaluate/iterate LLM-приложений | **Не брать** — завязано на LangSmith, мы на Langfuse |
| **langchain-skills** | `langchain-ai/langchain-skills` | LangChain/LangGraph/DeepAgents (фреймворки) | **Не брать по оси тестирования** — testing-скилла нет |
| **pypict-claude-skill** | `omkamal/pypict-claude-skill` | PICT pairwise/комбинаторный тест-дизайн | **Не брать** — узкая техника вне текущих потребностей |
| **playwright-skill** | `lackeyjb/playwright-skill` | Общая браузер-автоматизация | **Не брать** — дублирует webapp-testing + Playwright MCP |
| test-fixing / qa-engineer | community | Детект падающих тестов / QA-сабагент | **Не брать** — мелкие обвязочные |

### Вывод части 2

**Ведём testing-слайс на собственных принципах из research, без внешней зависимости.** Заимствуем как reference язык-агностичную дисциплину (superpowers TDD), концепции тест-дизайна и frontend-паттерны (citypaul), pytest-паттерны (wdm). Внешнего скилла, который имело бы смысл взять «как есть» зависимостью по ключевым осям (pytest-async + LLM-evals), нет. Опционально позже — собрать собственный проектный testing-skill из накопленного, по аналогии с тем, как авторские скиллы уже живут в `.claude/skills/`.

---

## Источники

Инвентаризация — по коду репозитория (пути указаны в тексте).

Skill discovery:
- Официальный репозиторий: https://github.com/anthropics/skills · https://github.com/anthropics/skills/tree/main/skills/webapp-testing
- https://github.com/obra/superpowers (skills/test-driven-development)
- https://github.com/citypaul/.dotfiles/tree/main/claude/.claude/skills (react-testing, front-end-testing, tdd, mutation-testing, test-design-reviewer, finding-seams, characterisation-tests)
- https://github.com/wdm0006/python-skills (testing-python-libraries)
- https://github.com/manikosto/claude-code-python-stack
- https://github.com/omkamal/pypict-claude-skill
- https://github.com/lackeyjb/playwright-skill
- https://github.com/langchain-ai/langchain-skills · https://github.com/langchain-ai/langsmith-skills
- Awesome-списки: https://github.com/travisvn/awesome-claude-skills · https://github.com/ComposioHQ/awesome-claude-skills · https://github.com/VoltAgent/awesome-agent-skills
