# S6 — Knowledge Sphere · run-log

Скоуп S6 (широкое покрытие: happy + основные ошибки). Автор тестов независим от
автора прод-кода. Возобновление после падения прошлого прогона: тест-файлы уже
лежали недописанными — осмотрены, сверены с прод-кодом, достроены до зелёного и
типобезопасности, с нуля не переписывались.

## Файлы (всё в `backend/tests/sphere/`)
- `conftest.py` — локальные фикстуры: `sphere_store` (свежий `InMemoryStore`),
  `install_sphere_service` (override `get_sphere_service` на реальный
  `LangGraphSphereService` поверх in-memory store; повторный вызов
  переустанавливает с guard'ом). Lifespan под `ASGITransport` не поднимается, а
  прод-провайдер читает `app.state.store` — поэтому шов handler → service → store
  гоняется по-настоящему, подменён только персистентный store.
- `test_sphere_api.py` — REST-контракт GET/PUT `/api/projects/{id}/sphere`
  (integration, authed `client`).
- `test_sphere_service.py` — `LangGraphSphereService` (sociable-unit поверх
  реального in-memory store).
- `test_knowledge_sphere_tools.py` — agent-tools `create/get/update/delete_section`
  (поведение на реальном in-memory store + сконструированный `ToolRuntime`).
- `test_ks_helpers.py` — чистые хелперы (`fuzzy_find_and_replace`, `format_index`,
  namespace/key) solitary-unit.

## Покрытые поведения
- **REST**: пустая сфера → 200 + blank content; PUT→GET round-trip секций
  (slugify заголовков, сохранение тела); замена контента удаляет выпавшие секции;
  ownership — чужой проект 404 (GET и PUT); несуществующий проект 404; битый UUID
  → 422; PUT без `content` → 422 validation-error (problem+json); INJECTION-вердикт
  → 422 `application/problem+json` с `type` …`security-policy-violation` и
  `reason="ks_write_rest"`; CLEAN-вердикт → контент персистится.
- **Service**: get на пустой → blank; парсинг markdown в секции; несколько секций
  сортируются по created_at; замена удаляет выпавшие; изоляция проектов по
  namespace; INJECTION → `SecurityPolicyViolationError(status=422,
  reason="ks_write_rest")` + запись не происходит; CLEAN/SUSPICIOUS
  (parametrize) → персистится, guard опрошен; без guard → персистится.
- **Agent-tools**: create пишет в store; дубль create → ошибка, оригинал цел;
  get отдаёт content; get отсутствующей → "not found"; update overwrite заменяет
  content; update patch-mode (fuzzy target) заменяет фрагмент; patch-конфликт →
  ошибка, контент цел; update описания; update отсутствующей → ошибка; delete
  удаляет; delete отсутствующей → ошибка; без store → `RuntimeError(Store)`; без
  context → `RuntimeError(AgentContext)`.
- **Хелперы**: namespace/key билдеры; fuzzy — короткий exact-match, короткий
  no-match, длинный near-match (1 опечатка в пределах адаптивной дистанции),
  длинный too-different, пустые входы (parametrize); format_index — пустой,
  сортировка по created_at + срез префикса, generic-вариант без key_fn.

## Дубли / инфра
- Postgres только под `client`-фикстурой (authed REST поверх реальной БД на
  транзакционном откате — из замороженного backend harness). Логика service и
  tools — на реальном in-memory LangGraph store (их настоящий коллаборатор), без
  БД. Guard — `StubGuard` из `packages/testing` (вердикт фиксирован; тестируем
  реакцию кода, не качество вердикта). Внешних эффектов с mock нет.

## Результат верификации
- `make test-scope P=backend/tests/sphere` — **45 passed**.
- `ruff check tests/sphere/` — clean; `mypy tests/sphere/` — clean.

## Точечные правки типобезопасности (только тест-файлы скоупа, прод не тронут)
- `StubGuard` duck-типизирует `SecurityGuard` → `cast(SecurityGuard, …)` в
  `conftest.py` и `test_sphere_service.py` (паттерн cast для тест-дублей, как в
  scope projects/security).
- `@tool` возвращает `BaseTool` без типизированного `.coroutine` → локальный
  хелпер `_coro` (cast к `StructuredTool.coroutine` как `Callable[..., Awaitable
  [str]]`) + алиасы `_create/_get/_update/_delete`. Тесты гоняют `.coroutine`
  напрямую: инъектируемый `runtime` исключён из публичной схемы tool'а, через
  `.ainvoke` его не передать.
- `ToolRuntime` — generic dataclass с реальными типами полей (`state: StateT`,
  `stream_writer: StreamWriter`). `None` для них не проходит; передаём benign
  реальные значения (`state={}`, `stream_writer=lambda _: None` — KS-tools их не
  читают) и параметризуем `ToolRuntime[AgentContext | None, dict[str, Any]]`.
  Реальный `ToolRuntime` сохранён (не подменён SimpleNamespace).
- `dict | None` индексирование результата store → хелпер `_require_section`
  (assert not None) для сайтов, где секция обязана существовать; `_section`
  остаётся для `is None`-проверок.

## Баги для Ф5
- Нет. Прод-код S6 ведёт себя по контракту; обходов/правок прода не потребовалось.

## Непокрытое и почему
- `_format_full_sphere`/`_parse_markdown_sections` без italic-описания (ветка
  fallback «первая строка как description») — частный парсинг-кейс прод-кода;
  основной путь (italic-описание) покрыт через service. Низкий риск, оставлено
  ради широты, не глубины (S6 — широкое покрытие, не критпуть для edge-глубины).
- Реальный Postgres-backed store агента не гоняется (testing.md: логику —
  на фейках/in-memory; PG-store — узкий integration-контур не в этом скоупе).
- Конкурентные запросы в одном тесте не делались (ограничение одной сессии
  харнесса, F2 в infra.md).

## Блокеры
- Нет. Замороженную инфру (`packages/testing`, общий conftest, Makefile) не
  трогал.
</content>
</invoke>
