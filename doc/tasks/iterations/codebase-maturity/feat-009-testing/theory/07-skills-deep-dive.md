# feat-009 · Разбор скиллов-кандидатов по тестированию (что внутри)

Ответ на вопрос «что эти скиллы из себя представляют и берём ли мы их». Прочитано **реальное содержимое**
скиллов (raw GitHub), не описания. Вывод вперёд: **тащить какой-либо скилл целиком смысла нет** — по нашему
ядру (async FastAPI + asyncpg + LangGraph + SSE на бэке, Vitest/RTL на фронте) ни один не закрывает то, ради
чего стоило бы заводить зависимость. Точечно стоит переиспользовать **три идеи** (не текст). Ведём слайс на
своих конвенциях + research, как ты и склонялся.

---

## 1. `testing-python-libraries` (wdm0006/python-skills)

**Что внутри.** Три файла: `SKILL.md` (~116 строк), `FIXTURES.md`, `HYPOTHESIS.md`.
- SKILL.md — мини-шпаргалка pytest: quick-start (`pytest`, `--cov`, `-x`, `-k`), конфиг в `pyproject.toml`
  (`branch=true`, `--cov-fail-under=85`), базовые паттерны (`parametrize`, фикстура, `mocker.patch`,
  `pytest.raises(match=)`), таблица принципов (Independent/Deterministic/Fast/Focused) + чеклист.
- FIXTURES.md — справочник по фикстурам: scopes, setup/teardown через `yield`, factory-fixtures (`make_user`),
  `tmp_path`. **Всё синхронное.**
- HYPOTHESIS.md — property-based: `@given`, стратегии, `@st.composite`, `assume()`, roundtrip-пример.

**Формат** — reference + базовые принципы (шпаргалка API), не workflow.

**«Library-oriented» — подтверждается, но мягче.** Заточенность под библиотеки видна в риторике (`--cov`,
public API, roundtrip, coverage-как-самоцель). НО обещанных tox/coverage-матриц в скилле фактически **нет** —
SKILL.md ссылается на `CI.md`, которого в репозитории не существует (битая ссылка). Как загружаемый контекст
это просто generic-pytest-карточка.

**Главный разрыв с нами — всё синхронное.** Ни `pytest.mark.asyncio`/anyio, ни `httpx.ASGITransport`, ни
asyncpg/транзакционных фикстур, ни LangGraph/SSE. Для нашего стека ядра не даёт ничего.

**Что переиспользуем (смыслом, не текстом):** coverage с `branch=true`, factory-fixtures, `tmp_path`,
`pytest.raises(match=)`, и **Hypothesis для чистых функций** (реальный кандидат — fuzzy-patch в knowledge-sphere,
парсеры/нормализаторы). **Рекомендация: не брать целиком**, держать Hypothesis-идею на виду.

---

## 2. `webapp-testing` (anthropics/skills, официальный)

**Что внутри.** `SKILL.md` (~95 строк) + `scripts/with_server.py` (менеджер жизненного цикла серверов) +
`examples/`. Суть прямым текстом: «To test local web applications, write native Python Playwright scripts.»
Workflow: decision tree (статический HTML vs динамическое приложение) → `with_server.py` поднимает
backend+frontend → reconnaissance-then-action (`goto` → `wait_for_load_state('networkidle')` → скриншот/DOM →
селекторы → действия). Headless chromium, `sync_playwright()`.

**Формат** — workflow + скрипты (агентный toolkit), не библиотека тестов.

**Это E2E/визуальная верификация, НЕ написание тест-наборов.** Однозначно **агентная UI-верификация и
отладка** (скриншоты, поведение, console-логи), одноразовые сценарии. Нет ни test runner'а, ни ассертов как
набора, ни структуры сьюта, ни CI. Это «глаза агента на фронте», а не Vitest/RTL-сьют, который коммитишь и
гоняешь в CI.

**Дублирование.** В основном **дублирует уже подключённый Playwright MCP** (навигация, скриншот, клики,
console). Сверх MCP даёт ровно одно: `with_server.py` — оркестрацию backend+frontend перед прогоном (MCP сам
сервера не поднимает).

**Рекомендация: не брать в тест-фундамент.** Для нашего фронтенд-юнита (Vitest/RTL в jsdom, без браузера) —
нерелевантен. Как агентный E2E почти весь перекрыт Playwright MCP; уникален только паттерн `with_server.py` —
держим на заметке, если вообще понадобится агентный smoke живого приложения поверх MCP.

---

## 3. `manikosto` (claude-code-python-stack)

**Skip — подтверждается прямой цитатой.** `pytest-oop-patterns` содержит правило «No Bare Functions»:
дословно «Every test MUST be inside a class. This is non-negotiable», с обязательными base-классами и
`@allure.step` на каждом методе — **Allure вшит в архитектуру, не опционален**. `api-testing-patterns` — про
black-box QA задеплоенного сервиса по реальному HTTP (не in-process ASGITransport), тоже с Allure. Даже
относительно чистый `python-testing` несёт TDD/coverage-банальности и идеологически связан с OOP+Allure.

**Конфликт с конвенциями прямой:** у нас функциональные pytest-тесты, Allure не используется. **Skip всех трёх.**

---

## Итог и решение

| Скилл | Что это | Решение |
|-------|---------|---------|
| `testing-python-libraries` | Синхронная generic-pytest-шпаргалка; tox/CI-файл отсутствует | Не брать; переиспользовать идею Hypothesis + coverage `branch=true` |
| `webapp-testing` | Агентная E2E-верификация живого UI; дублирует Playwright MCP | Не брать; паттерн `with_server.py` — на заметку |
| `manikosto/*` | OOP + Allure framework для black-box API | Skip (конфликт с конвенциями) |

**Решение архитектора (фиксирую):** внешний testing-skill зависимостью **не берём**. Ведём слайс на
собственных тест-конвенциях + материале research. Переиспользуем три идеи смыслом: (1) Hypothesis для чистых
функций (кандидат — fuzzy-patch knowledge-sphere), (2) coverage `branch=true` как настройку, (3)
`with_server.py`-паттерн — только если понадобится агентный E2E поверх Playwright MCP.

**Чего нет ни в одном скилле и что в любом случае пишем сами:** async-фикстуры PostgreSQL (откат транзакций),
ASGI-клиент + auth-фикстура, тестирование LangGraph-графа и SSE-стриминга, фейки LLM/guard и Langfuse,
контрактные тесты main↔siem. Это ядро нашей тестовой инфраструктуры — источника на стороне нет, и это
нормально (тесты — область с устоявшимся фундаментом, его достаточно).

**Опциональный задел (не в этой итерации):** собрать **свой** проектный testing-skill из накопленных
конвенций feat-009 — по аналогии с тем, как в фазе появились langgraph-patterns и др. Кандидат в backlog.

## Источники
- https://github.com/wdm0006/python-skills — `skills/testing-strategy/{SKILL,FIXTURES,HYPOTHESIS}.md`
- https://github.com/anthropics/skills — `skills/webapp-testing/` (`SKILL.md`, `scripts/with_server.py`)
- https://github.com/manikosto/claude-code-python-stack — `skills/{python-testing,pytest-oop-patterns,api-testing-patterns}/`
