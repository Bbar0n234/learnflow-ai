# Инженерия тестов на Python: pytest под наш стек

Документ — теоретический разбор для архитектора. Цель: понять, как современная (2025–2026) инженерия pytest-тестов ложится на наш стек — FastAPI, async SQLAlchemy 2.x, PostgreSQL, Alembic, structlog, uv workspace monorepo (`backend/` + `services/siem-service/` + `packages/`). Не план реализации — учебная база под развилки Фазы 1.

---

## 1. Async-движок тестов

### pytest-asyncio сменил мажор

Серия `0.2x` закончилась — актуальная линия **1.x**. Главные следствия:

- Фикстура `event_loop` **упразднена**. Раньше её переопределяли, чтобы расширить scope цикла; теперь так делать нельзя.
- Scope событийного цикла задаётся аргументом **`loop_scope`** у маркера и фикстуры:
  `@pytest.mark.asyncio(loop_scope="session")`, `@pytest_asyncio.fixture(loop_scope="session")`.
- Два режима discovery:
  - **strict** (дефолт) — каждый async-тест нужно явно пометить `@pytest.mark.asyncio` или сделать `@pytest_asyncio.fixture`;
  - **auto** — любой `async def`-тест подхватывается без маркера. Меньше церемоний.
- По умолчанию каждый тест получает свой event loop на scope `function` — максимальная изоляция.

### Альтернатива: anyio

Официальная документация FastAPI тестирует через `@pytest.mark.anyio` (плагин `anyio`, не pytest-asyncio), потому что Starlette/FastAPI сами на anyio — это позволяет гонять тесты и на asyncio, и на trio. Это **конкурент** pytest-asyncio, а не дополнение: в проекте выбирают что-то одно. Выгоду anyio даёт только при потребности в trio-совместимости.

> **Грабли event loop scope.** При session-scoped engine (asyncpg) и function-scoped event loop соединение, созданное в одном loop, нельзя использовать в другом → `RuntimeError: Future attached to a different loop`. Лечение: согласовать `loop_scope` фикстур engine и тестов (обычно весь async-стек держат на `session`/`package` loop scope).

---

## 2. HTTP-тесты FastAPI

`TestClient` (синхронный, на `requests`) больше не дефолт для async-кода. Актуальный паттерн — `httpx.AsyncClient` поверх `ASGITransport`: приложение вызывается в памяти, без поднятия сокета.

```python
from httpx import ASGITransport, AsyncClient

async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
    resp = await client.get("/items/")
```

**Нюанс lifespan.** `AsyncClient` сам по себе **не запускает lifespan-события**. Если в lifespan создаётся пул БД / прогреваются ресурсы — варианты:

- обернуть в `LifespanManager` из `asgi-lifespan`;
- либо инжектить ресурсы фикстурами и переопределять их через `app.dependency_overrides` (предпочтительно для подмены БД-сессии на тестовую транзакцию).

### Фикстура аутентифицированного клиента

Защита стоит на **каждом приватном endpoint**, поэтому integration-тестам нужна фикстура, ходящая «как залогиненный пользователь». Без неё почти весь HTTP-слой недоступен тесту. Два подхода:

- **(а) Override `Depends`-провайдера `current_user`** через `app.dependency_overrides` на тест-юзера. Быстро, без минта реальных JWT, обходит крипто. Это **дефолтная фикстура** для тестов, которые проверяют не auth, а защищённую функциональность за ним.
- **(б) Реальный логин-флоу** через `/auth/login` с получением access/refresh-токенов и хождением с ними. Честнее (заодно проверяет auth-подсистему), но медленнее и связывает каждый тест с auth. Применяем **узкой группой именно на auth-критпуть**: логин, refresh-ротация, отзыв токена.

Surface: `backend/app/services/auth.py`, `backend/app/api/routes/auth.py`, `backend/app/repositories/refresh_token.py`. Выбор фикстуры — развилка **B7** в `decisions-phase1.md`.

---

## 3. Тестовая БД

### Три стратегии

| Стратегия | Плюсы | Минусы |
|---|---|---|
| **Real Postgres + transactional rollback** (`join_transaction_mode="create_savepoint"`, откат внешней транзакции в teardown) | Быстрее всего после старта; полная изоляция; реальный диалект (JSONB, массивы, CTE, constraints) | Код под тестом не должен сам открывать/коммитить транзакцию верхнего уровня; нюансы с async loop scope |
| **Real Postgres + truncate/recreate схемы на тест** | Проще ментально; работает даже если код вызывает свой `commit`/transaction | Медленнее (TRUNCATE/DDL каждый тест); нужен аккуратный порядок таблиц |
| **SQLite вместо Postgres** | Без Docker, мгновенно | **Антипаттерн.** Расходится с Postgres по типам и поведению (нет JSONB/массивов, иная семантика constraints) — даёт ложную уверенность; `aiosqlite` не покрывает savepoint-паттерны как Postgres |

**Консенсус 2025–2026:** реальный Postgres через **testcontainers** (session-scoped контейнер) + **транзакционный откат на каждый тест**. SQLite-замена — антипаттерн для проектов, реально использующих фичи Postgres (а мы используем JSONB/Postgres-специфику).

### Канонический rollback в SQLAlchemy 2.0

В 2.0 рецепт официально упрощён — больше **не нужны** event-хендлеры для перезапуска SAVEPOINT:

1. открываешь внешнюю транзакцию на `Connection`/`AsyncConnection`;
2. биндишь к ней `Session` с `join_transaction_mode="create_savepoint"`;
3. в teardown — `rollback()` внешней транзакции.

Тестируемый код свободно зовёт `session.commit()`, но на деле всё живёт внутри savepoint и откатывается.

### Подготовка схемы: миграции vs create_all vs гибрид

| Подход | Что проверяет | Цена |
|---|---|---|
| **Alembic-миграции** (`upgrade head`) | Что миграции применяются и совпадают с моделями; путь как в проде | Медленнее |
| **`Base.metadata.create_all()`** | Только модель, **не реальную БД** — дрейф миграций остаётся незаметным | Быстро |
| **Гибрид** | Масса тестов на `create_all` + отдельный тест/CI-шаг «миграции от нуля до head + autogenerate пуст» | Баланс |

У нас **hard-rule на autogenerate-миграции** — логично, чтобы тестовая БД поднималась тем же путём, что прод (`alembic upgrade head`), плюс отдельный быстрый страж дрейфа: «autogenerate против тестовой БД ничего не видит». Если прогон всех миграций окажется заметно медленным — компромисс гибрида.

### Обратимость и две истории миграций

Два момента, специфичных для нас:

- **Downgrade тоже тестируем.** Upgrade-only проверки не ловят необратимые миграции. Для критичных ревизий нужен тест цикла `upgrade → downgrade → upgrade` (или хотя бы `downgrade` на один шаг) — иначе откат в проде окажется сломанным ровно в тот момент, когда он нужен.
- **Две независимые alembic-цепочки.** В проекте раздельные истории миграций — backend (~7 версий) и siem-service (своя). Их тестовая подготовка идёт **раздельно**, и страж «autogenerate пуст» заводится **на каждую из двух** против своей схемы. Смешивать их в одном прогоне нельзя.

### Параллельный прогон (pytest-xdist) и изоляция БД

Ускорять набор `pytest -n` (xdist) — естественно, но тут общая тестовая БД становится **точкой конфликта**: воркеры исполняются параллельно и топчут данные друг друга. Нужна изоляция per-worker:

- отдельная схема или БД на воркер (имя воркера доступно через `PYTEST_XDIST_WORKER`) — каждый воркер поднимает/мигрирует свою;
- либо транзакционная изоляция (savepoint-rollback), совместимая с параллелизмом, при условии, что соединения не делятся между воркерами.

Это **другое измерение параллельности**, чем фан-аут Фазы 3: там параллельны тестировщики-АГЕНТЫ, пишущие разные файлы (конфликт по коду), здесь — параллельны процессы-воркеры pytest, исполняющие готовые тесты (конфликт по данным БД). Одно не заменяет другое.

---

## 4. conftest и фикстуры

- **Иерархия `conftest.py` — это фича, а не дублирование.** Корневой держит кросс-проектные фикстуры (engine, loop scope, общие билдеры); conftest рядом с пакетом — специфику пакета. pytest сам собирает фикстуры вверх по дереву, переопределение работает по близости.
- **Scope — баланс скорости и изоляции.** Дорогое и неизменяемое (Docker-контейнер БД, engine, прогон миграций) → `session`. Состояние, которое тест меняет (соединение/транзакция/сессия БД, HTTP-клиент) → `function`. Антипаттерн: `session`-scoped мутабельное состояние → протечки между тестами.

---

## 5. Тестовые данные: фабрики

- **factory_boy всё ещё без нативного async** (issue #679 открыт). Для async-сессий SQLAlchemy используют либо обёртку **`async-factory-boy`**, либо синхронные фабрики со стратегией **build** (генерят объект без привязки к async-сессии) + ручной `session.add`.
- **Когда factory_boy окупается:** много полей и связей (`SubFactory`, `Faker`, `Sequence`, `post_generation` убирают шум). Минус — «магия», async-не-нативность.
- **Ручные билдеры** проще и прозрачнее на маленькой модели данных.
- **Гибрид (рекомендуемый):** factory_boy для генерации значений + явная async-сессия фикстуры для персистентности.
- **Fixture-factory паттерн:** фикстура, **возвращающая функцию**-конструктор. Удобна, когда в одном тесте нужно несколько разных экземпляров с вариациями.

---

## 6. Coverage

- **pytest-cov поверх coverage.py.** Включать **branch coverage** (`--cov-branch`): строковое покрытие переоценивает проверенность (ветка `if` без `else` считается покрытой при заходе только в одну сторону).
- **Процент как цель — вреден** (Goodhart): догма «100%» провоцирует тесты-пустышки. Практика: **floor в CI** (например 80%) как страж от регресса, мерить тренд, не покрывать тривиальное (генерённый код, `__repr__`, `if TYPE_CHECKING`).
- **Per-package в монорепо**, а не общим котлом — иначе хорошо покрытый пакет маскирует дыры в другом.
- `--cov-report=term-missing` для точечного поиска непокрытых веток полезнее погони за числом.

---

## 7. Property-based и mutation testing

**Hypothesis — точечно.** Окупается там, где есть свойство/инвариант поверх широкого пространства входов: round-trip сериализация↔десериализация, парсеры/валидаторы, нормализация, кодеки, числовые/датовые границы, идемпотентность. Hypothesis сам ищет минимальный контрпример (shrinking). **Не окупается** для конкретной бизнес-логики с фиксированными ожиданиями и для тестов с тяжёлыми побочными эффектами (каждый пример = запрос к БД/сети). Кандидаты у нас — чистые функции SIEM-парсинга/нормализации, сериализаторы.

**Mutation testing (mutmut v3 / cosmic-ray)** — мутирует код и проверяет, ловят ли тесты мутации; измеряет **реальную силу** тестов лучше coverage. Дорого по времени. Реалистично: не в обычном CI, а как разовый/периодический аудит критичных модулей (auth, парсинг). Нишевый, но зрелый инструмент.

---

## 8. Раскладка в монорепо

- **Тесты живут в своём пакете** (`<package>/tests/`), рядом со своим `pyproject.toml` и своими dev-зависимостями (`[dependency-groups] dev` / `[project.optional-dependencies]`). Согласуется с нашим правилом «Python-команды запускаются из директории пакета».
- **Общие тест-утилиты** (фикстуры, фабрики, билдеры) — в выделенном общем пакете (кандидат — `packages/testing`), который пакеты подключают как dev-зависимость. DRY и единый источник фабрик; цена — +1 пакет в workspace.
- **Запуск** — цель Makefile, прогоняющая `pytest` в каждом пакете (либо корневой агрегатор с per-package отчётами покрытия).

### Контрактные тесты между сервисами

Main app и siem-service связаны общим пакетом `packages/siem-contracts` (`vocabulary.py` — словарь событий). Дрейф этого контракта — отдельный наблюдаемый риск, и закрывается он естественно «тестами в своём пакете»: тесты-стражи словаря (значения, сериализация событий, что обе стороны используют один словарь) живут в `packages/siem-contracts/tests` как тесты библиотеки. Детали и форма — развилка **B8** в `decisions-phase1.md`.

---

## 9. Нейминг, маркеры, логи

- Единый стиль: `test_<unit>_<condition>_<expected>`.
- Маркеры `@pytest.mark.unit` / `integration` / `slow` для селективного прогона (быстрый unit-гейт в pre-commit, полный — в CI).
- `parametrize` для таблиц «вход → ожидание» вместо копипасты тестов.
- **structlog в тестах:** для проверки логирования — `structlog.testing.capture_logs` (контекст-менеджер, перехватывает события без реального вывода), чище, чем `caplog`.

---

## Что это значит для нас

1. **Async-движок** — pytest-asyncio 1.x в `asyncio_mode="auto"` на весь монорепо (anyio не нужен без trio). Согласовать `loop_scope` async-фикстур, чтобы не ловить «different loop».
2. **HTTP-тесты** — `httpx.AsyncClient` + `ASGITransport`, зависимости через `app.dependency_overrides`, lifespan через `LifespanManager` либо инъекцию ресурсов фикстурами.
3. **БД** — testcontainers Postgres (session-scoped) + транзакционный rollback `create_savepoint` на тест; реальный Postgres важен из-за JSONB/специфики.
4. **Схема** — миграциями (как в проде) + страж autogenerate-дрейфа; гибрид, если миграции медленны.
5. **Данные** — factory_boy + `async-factory-boy`/build-стратегия; базовые фабрики в общем пакете; fixture-factory для вариаций.
6. **Coverage** — `--cov-branch`, per-package, floor ~80% как страж, не KPI.
7. **Hypothesis** — точечно на чистые функции; mutation testing — периодический аудит ядра.
8. **Раскладка** — тесты в своём пакете, общие утилиты в `packages/testing`, запуск через Makefile.

**Развилки на согласование (Фаза 1):** pytest-asyncio vs anyio · testcontainers vs `make docker-up-db` · миграции vs create_all vs гибрид · savepoint-rollback vs truncate · отдельный пакет `packages/testing` vs дублирование · coverage floor и нужно ли mutation testing · фикстура аутентифицированного клиента (B7) · контрактные тесты main↔siem (B8) · изоляция БД под xdist при параллельном прогоне.

---

## Источники

- pytest-asyncio — Concepts (strict/auto, `loop_scope`, 1.x): https://pytest-asyncio.readthedocs.io/en/latest/concepts.html
- FastAPI — Async Tests (`httpx.AsyncClient` + `ASGITransport`, `pytest.mark.anyio`, LifespanManager): https://fastapi.tiangolo.com/advanced/async-tests/
- SQLAlchemy 2.0 — Joining a Session into an External Transaction (`join_transaction_mode="create_savepoint"`): https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites
- SQLAlchemy — asyncio extension: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- testcontainers-python 2.0: https://testcontainers-python.readthedocs.io/
- Testcontainers for Python — getting started: https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/
- factory_boy — async support (issue #679): https://github.com/FactoryBoy/factory_boy/issues/679
- async-factory-boy: https://pypi.org/project/async-factory-boy/
- factory_boy — Using with ORMs: https://factoryboy.readthedocs.io/en/stable/orms.html
- Hypothesis: https://hypothesis.readthedocs.io/
- coverage.py — branch coverage: https://coverage.readthedocs.io/en/latest/branch.html
- pytest-cov: https://pytest-cov.readthedocs.io/
- mutmut (v3): https://mutmut.readthedocs.io/
