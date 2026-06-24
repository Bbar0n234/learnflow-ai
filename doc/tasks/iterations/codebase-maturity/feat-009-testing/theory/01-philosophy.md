# Философия тестирования — теория под LearnFlow AI

Документ-черновик для разбора с архитектором (Фаза 0 feat-009). Цель — не каталог моделей, а ответ на вопрос: **что, на каком уровне и зачем мы тестируем** в нашей конкретной системе — слоистый backend (`handlers → services → repositories` на FastAPI/SQLAlchemy), agent runtime на чистом LangGraph и frontend на React/TS.

---

## 1. Суть вперёд: о чём вообще спор

Все «формы» тестирования (пирамида, trophy, honeycomb, diamond) отвечают на один и тот же вопрос: **сколько усилий вкладывать в каждый уровень тестов** при ограниченном времени. Они различаются не принципами, а контекстом, под который их придумывали.

Главное, что нужно вынести до всякой формы (Justin Searls, цитируют и Dodds, и web.dev):

> Пиши выразительные тесты, которые задают чёткие границы, бегут быстро и надёжно, и падают только по полезным причинам.

И второй принцип (Kent C. Dodds):

> Чем больше тест похож на то, как ПО реально используется, тем больше уверенности он даёт.

ROI теста = **уверенность / время**. Форма пирамиды — лишь следствие этой формулы, а не самоцель.

---

## 2. Модели и их trade-offs

| Модель | Расклад | Под что придумана | Слабость |
|--------|---------|-------------------|----------|
| **Пирамида** (Cohn→Fowler) | много unit → мало e2e | богатая доменная логика, изолируемая от I/O | переоценивает unit, провоцирует mock-heavy и хрупкость; молчит про статанализ |
| **Trophy** (Dodds) | static → unit → **integration (основа)** → e2e | **frontend и монолит в одних руках** (Dodds прямо оговаривает: не для микросервисов) | «static» нужен потому, что в JS его нет по умолчанию |
| **Honeycomb** (Spotify) | мало «integrated» → **много integration** → немного на детали | микросервисы: сложность во взаимодействии, не внутри | для монолита смещает фокус не туда |
| **Diamond** | unit прорежён, центр тяжести — integration | реакция на эрозию 100%-unit при рефакторинге | — |
| **Ice-cone** | всё руками / e2e | — | **признанный антипаттерн**: дорого, медленно, флаки |

### Почему спор о форме во многом семантический

Fowler разводит два смысла слова «unit»:

- **solitary unit** — коллабораторы заменены дублями (изолированный тест);
- **sociable unit** — реальные коллабораторы участвуют.

То, что honeycomb-адепты зовут «integration», — это ровно fowler-овский **sociable unit**. Спор «пирамида против honeycomb» сводится к тому, что считать словом «unit». Поэтому форма — вторична, а первичен стиль: **sociable по умолчанию, solitary — только на болезненных границах** (внешние сервисы, недетерминизм, скорость).

Google вообще отказывается от scope-терминологии в пользу **test size**, потому что для CI важны скорость и детерминизм, а не «размер»:

- **small** — один процесс, без I/O / сети / диска / сна (всё внешнее — дублями);
- **medium** — одна машина, можно localhost и реальную БД;
- **large** — несколько машин / внешние системы.

Эта оптика полезна нам для разделения быстрого pre-commit-прогона и полного CI.

---

## 3. Что тестируем по нашим слоям

Общая рамка для backend — **гибрид trophy/diamond в classic (sociable) стиле**: статанализ как фундамент, тонкий слой solitary-unit на чистую логику, основная масса — sociable-unit на сервисы и integration на репозитории + критпуть хендлеров, тонкий smoke на главный journey.

### Handlers — тонкие, отдельным unit НЕ покрываем

Хендлеры у нас тонкие, своей логики почти нет. Их поведение ловится **integration-тестом через ASGI-клиент** (`httpx.AsyncClient` + `ASGITransport`) на критпути. Проверяем ровно то, что живёт в слое хендлера: маршрутизацию, валидацию Pydantic, статус-коды, сериализацию, auth/permissions, маппинг ошибок в HTTP. По Google это medium-тест.

### Services — ядро тестирования, sociable-unit

Здесь бизнес-логика, здесь максимум ценности. Реальные коллабораторы (другие сервисы, чистые функции), дубли — **только на границах I/O**: внешние API, LLM, время, рандом. Именно здесь применяем «test behavior, not implementation».

### Repositories — integration против реальной Postgres

**Не SQLite и не мок SQLAlchemy** — иначе диалект-дрейф (теряем JSONB, массивы, поведение constraints) и проверка мока вместо запроса. Реальный Postgres (Docker/testcontainers), изоляция через транзакционный rollback или truncate между тестами (hermetic).

### Утилиты / чистые функции — дешёвый solitary-unit, по вкусу

### Что НЕ покрываем

Тривиальные DTO/Pydantic-схемы без логики, геттеры, glue/конфиг-склейку, сам фреймворк, приватные методы (через публичный контракт), автоген.

---

## 4. Agent runtime — особый случай (два режима)

Агент разделяется надвое по природе тестируемого:

**Детерминированная обвязка → обычные тесты.** Узлы графа, conditional edges/routing, state-reducers, tool-функции, парсинг structured output, переходы Command/HITL (interrupt/resume) — это детерминированный код. Тестируем unit/integration с **застабленным LLM** (fake, возвращающий канонический ответ, в т.ч. запрограммированный `tool_call`). Чистый LangGraph хорошо тестируется на уровне графа.

**Качество LLM-выходов → НЕ unit-тесты, а evals.** LLM недетерминирован, `assert == expected` не работает. Это **dataset + experiment runner + evaluator** (Langfuse уже в стеке): регрессия на качество с порогом, а не pass/fail на строку. Оценка эвристикой или LLM-as-judge, офлайн/по расписанию — отдельный контур, не CI-гейт.

Tools, ходящие в knowledge-sphere/БД, тестируем как репозитории — integration.

> Прямое следствие для нас: непроверяемость guard- и agent-путей (находка feat-006) — это про *детерминированную обвязку*, которую сейчас нельзя застабить, потому что модель создаётся внутри кода. Решается швом инъекции модели — см. отдельный документ по LLM-тестированию.

---

## 5. Frontend — trophy по Dodds

Static (tsc + ESLint) — фундамент (уже gate). Основная масса — **integration через Testing Library + MSW** (мок HTTP на сетевой границе); немного чистых unit (хуки/утилиты); немного e2e (Playwright) на главные journey. Принцип устойчивости к рефактору: искать элементы по роли/тексту, как пользователь, а не по `className` или инстансам компонентов.

---

## 6. Таксономия test doubles (Meszaros / Fowler)

Чтобы команда говорила на одном языке:

| Дубль | Что делает |
|-------|-----------|
| **Dummy** | заполняет параметр, не используется |
| **Stub** | отдаёт заранее заданные ответы (state verification) |
| **Spy** | stub, который ещё и записывает, как его вызывали |
| **Mock** | заранее запрограммирован ожиданиями вызовов (behavior verification) |
| **Fake** | рабочая упрощённая реализация (in-memory БД, fake LLM) |

**Правило:** предпочитать **fakes и stubs**; **mock — только когда сам факт/форма вызова и есть проверяемое поведение** (отправили письмо, дёрнули внешний API). Mock-heavy ведёт к хрупкости и «тестированию моков»; Google от абуза дошёл до лозунга «no more mocks». Каждое mock-ожидание — это привязка к реализации коллаборации.

---

## 7. Поперечные принципы

**Test behavior, not implementation.** Тестируем наблюдаемое поведение через публичный контракт (вход → выход / побочный эффект), а не внутренние вызовы, приватные методы и структуру. Диагностический признак привязки к реализации: **тест падает при рефакторинге, который не менял поведение** (change-detector / brittle test).

**Авто vs ручное.** Автоматизируем всё детерминированное и повторяемое: unit, integration, контрактные, smoke, критичные e2e-journey. Руками: exploratory/usability, оценка UX, приёмка фичи, разовые дорогие сценарии. Автоматизация **дополняет, а не заменяет** ручное — освобождает людей на важное. E2E/UI автоматизируем только для критичных journey (дорого, медленно, флаки).

**Coverage — диагностика, не цель.** Процент как цель вреден (Goodhart; Seemann, Fowler): 100% добиваются бессмысленным тестом без ассертов (false-green). Как диагностика полезен: находить непокрытые ветки, следить за трендом, гейт «не понижать». Google: мерить только на small-тестах. Что мерить вместо числа: **mutation testing** (убивает ли тест внесённую мутацию — проверка качества ассертов), флейкость, скорость suite, defect escape rate.

**DoD по тестам.** Норму «каждый функционал обязан иметь тесты» принимаем в трактовке «**каждое поведение/контракт покрыто на адекватном уровне**», а не «каждая строка имеет unit». Минимум для новой фичи: (1) unit на нетривиальную логику сервиса; (2) integration на критпуть (handler ↔ service ↔ repository/БД); (3) проходит static. Для агента — unit на обвязку + при необходимости eval-кейс в датасет. Исключения — осознанно и с обоснованием (тривиальный код, glue, помеченные спайки, UI-полировка). Принцип Google: **тесты — это production code** (ревью, поддержка, рефакторинг хрупких и медленных).

---

## 8. Антипаттерны (чего избегаем)

- **Flaky tests** — главный враг, источник недоверия ко всему suite. Причины: время, рандом, сеть, порядок выполнения, гонки, разделяемое состояние. Лечение: hermetic-тесты, изоляция, контроль времени/рандома, без sleep, карантин + починка (а не слепой retry).
- **False-green / assertion-free** — тест без ассертов или с `try/except`, который не падает никогда. Покрытие есть, ценности ноль.
- **Mock-heavy** — ассертим взаимодействие с дублями вместо поведения.
- **Change-detector / brittle** — over-specify ожиданий, тесты ломаются от несвязанных изменений и тормозят рефакторинг.
- **Ice-cone** — перевёрнутая пирамида, всё руками/e2e.
- **Coverage-driven** — тесты ради процента.

---

## Что это значит для нас

Берём **classic (sociable) стиль** на слоистом backend: статанализ как фундамент, услуги (services) — ядро тестов на реальных коллабораторах с дублями только на I/O-границах, репозитории — integration против реальной Postgres, хендлеры — через ASGI-клиент на критпути, утилиты — точечный solitary-unit. Агент делим на детерминированную обвязку (обычные тесты на fake-LLM) и качество выходов (отдельный eval-контур на Langfuse, вне CI-гейта). Frontend — trophy с упором на integration через MSW. Coverage держим как диагностику, DoD формулируем через поведение, а не строки, и осознанно воюем с flaky и false-green как с главными разрушителями доверия к suite.

---

## Источники

- Kent C. Dodds, «The Testing Trophy and Testing Classifications» — https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications
- Kent C. Dodds, «Write tests. Not too many. Mostly integration.» — https://kentcdodds.com/blog/write-tests
- Martin Fowler, «On the Diverse And Fantastical Shapes of Testing» (2021) — https://martinfowler.com/articles/2021-test-shapes.html
- Martin Fowler, «UnitTest» (solitary vs sociable) — https://martinfowler.com/bliki/UnitTest.html
- Martin Fowler, «Mocks Aren't Stubs» (таксономия Meszaros) — https://martinfowler.com/articles/mocksArentStubs.html
- Martin Fowler, «TestPyramid» — https://martinfowler.com/bliki/TestPyramid.html
- web.dev (Ramona Schwering, Google), «Pyramid or Crab? Find a testing strategy that fits» — https://web.dev/articles/ta-strategies
- Software Engineering at Google, ch.11 «Testing Overview» — https://abseil.io/resources/swe-book/html/ch11.html
- Google Testing Blog, «Test Behavior, Not Implementation» — https://testing.googleblog.com/2013/08/testing-on-toilet-test-behavior-not.html
- Google Testing Blog, «Where do our flaky tests come from?» — https://testing.googleblog.com/2017/04/where-do-our-flaky-tests-come-from.html
- Mark Seemann (ploeh), «Code coverage is a useless target measure» — https://blog.ploeh.dk/2015/11/16/code-coverage-is-a-useless-target-measure/
- Spotify Engineering, «Testing of Microservices» (honeycomb) — https://engineering.atspotify.com/2018/01/testing-of-microservices/
- Langfuse, «A Practical Guide to Automated Testing for LLM Applications» (2025) — https://langfuse.com/blog/2025-10-21-testing-llm-applications
- Hamel Husain, «Your AI Product Needs Evals» — https://hamel.dev/blog/posts/evals/
