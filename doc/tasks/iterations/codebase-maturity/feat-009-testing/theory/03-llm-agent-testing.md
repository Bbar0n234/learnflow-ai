# Тестирование LLM- и агентного слоя

> Теоретический черновик к feat-009. Аудитория — архитектор. Цель — разобраться, *как вообще* тестируют LLM-приложения на нашем стеке (чистый LangGraph, `ReasoningChatOpenAI`, security guard, SSE-стрим, Langfuse) и какие решения нам предстоит принять.

## Главный вывод: дело в шве — и он во многом уже есть

Находка из feat-006 звучала так: целый класс путей нельзя проверить без живого LLM-ключа — add-time security blocks (custom instructions / sphere editor / MCP form, HTTP 422), runtime `security_block` в чате, запись в Knowledge Sphere через guard (без ключа guard деградирует в CLEAN и контент не персистится), весь агентный SSE-стрим. Естественное прочтение: «нам не хватает тестовых инструментов под LLM». **Это прочтение неверно** — инструменты есть и зрелые. Вопрос в шве (seam): есть ли точка, куда тест подставит фейковую модель.

**Сверка по коду показала, что шов в значительной части уже есть:**

- `build_graph(model: BaseChatModel, ...)` (`backend/app/agent/graph.py:193`) **уже принимает модель параметром**.
- `LLMClassifier(llm: BaseChatModel, ...)` (`backend/app/agent/security/classifier.py:34`) **уже инъектируемый**, программирован против `BaseChatModel`; guard-модель создаётся в composition root (`backend/app/main.py:342` `create_guard_llm` → `:365` `LLMClassifier(llm=...)`) и прокидывается внутрь.

Значит логику графа и guard **можно тестировать фейком уже сейчас, без правок прода** — вызывая `build_graph(model=fake, ...)` и `LLMClassifier(llm=fake, ...)` напрямую. Единственная точка без шва — **`GraphFactory.build()`** (`backend/app/agent/graph_factory.py:52`): там agent-LLM создаётся внутри через `create_llm_from_config(...)`, плюс сам composition root в lifespan. Недоступен только путь «через фабрику / полное приложение».

Поэтому задача Фазы 2 — не «ввести шов с нуля» и не «переписать архитектуру», а **локально дотянуть шов в одной точке (`GraphFactory`)**, чтобы стал проверяем и полный путь. Это снижает риск и объём C1 по сравнению с тем, как боль выглядела из feat-006.

```
УЖЕ ПРОВЕРЯЕМО (шов есть):
   build_graph(model=...)  /  LLMClassifier(llm=...)
                                       ▲
              прод: реальная модель      тест: GenericFakeChatModel([...])

ОСТАЁТСЯ ДОТЯНУТЬ (шва нет):
   GraphFactory.build()  ──создаёт──>  create_llm_from_config(...)  ──сеть──>  OpenAI
                                       ▲
                          тест пока не может вклиниться здесь
```

---

## 1. Шов инъекции модели

`build_graph` и `LLMClassifier` уже принимают модель параметром (см. главный вывод) — там тесты пишутся фейком без правок прода. Открытая точка одна: `GraphFactory.build()` создаёт agent-LLM внутри. Вопрос развилки — **как дотянуть шов до фабрики**, чтобы стал проверяем путь «через полное приложение». Три способа.

### Вариант (а): параметр/фабрика модели в `GraphFactory` — **рекомендуемый**

`GraphFactory` принимает model-factory (callable), переопределяемую в тестах; прод передаёт текущую `create_llm_from_config`.

- **Плюс:** явная зависимость, **нет глобального состояния** — в духе hard-rule «никаких module-level синглтонов». Тест передаёт фабрику фейков, прод — реальную. Изменение локальное (один конструктор фабрики), не трогает уже инъектируемые `build_graph` / `LLMClassifier`.
- **Минус:** model-factory приходится пробросить до точки сборки — чуть больше «проводки».

### Вариант (б): dependency-override на уровне приложения

Провайдер модели в `app.state`, подменяется в тест-фикстуре через `app.dependency_overrides`.

- **Плюс:** единый override перекрывает весь composition root; удобно для integration-тестов полного приложения.
- **Минус:** завязывает тест на устройство lifespan / `app.state`; глобальная точка вместо явного аргумента. Связано с изоляцией `app.state` в тестах (см. §4).

### Вариант (в): тестировать преимущественно на уровне `build_graph` / `LLMClassifier`

Где шов уже есть — туда и пишем основную массу тестов; через `GraphFactory` гоняем лишь тонкий integration (с monkeypatch точки создания модели как разовым приёмом).

- **Плюс:** минимум продакшн-правок.
- **Минус:** «полный» путь через фабрику остаётся слабее покрыт; monkeypatch путей импорта хрупок и недопустим как постоянная стратегия.

**Рекомендация:** (а) — лечит единственную архитектурную точку без шва, под наши же конвенции. Решение за архитектором, но локальное и низкорисковое: бо́льшая часть тестов логики и guard вообще не требует продакшн-правок.

---

## 2. Подмена модели: `GenericFakeChatModel`

Ключевой принцип: **код программируем против `BaseChatModel` / `Runnable`, а не против `ReasoningChatOpenAI`.** Тогда в шов встаёт любой fake-наследник `BaseChatModel`.

Канонический инструмент сегодня — **`GenericFakeChatModel`** из `langchain_core.language_models.fake_chat_models`:

- принимает итератор ответов (строки или готовые `AIMessage`), отдаёт по одному за `invoke`;
- поддерживает и обычный, и streaming-режим;
- **умеет `tool_calls`** — главное для ReAct-агента. В `AIMessage(content="", tool_calls=[ToolCall(name=..., args=..., id=...)])` мы программируем ровно тот tool-call, который агент должен сделать. Это позволяет детерминированно прогнать петлю «модель → tool → модель → ответ».

```python
from langchain_core.messages import AIMessage, ToolCall
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

fake = GenericFakeChatModel(messages=iter([
    AIMessage(content="", tool_calls=[ToolCall(name="search_ks", args={"q": "x"}, id="1")]),
    AIMessage(content="Готовый ответ после tool-call"),
]))
```

Старые `FakeListChatModel` / `FakeMessagesListChatModel` тоже существуют, но беднее — у них нет нормального tool-calling. **Для агента берём `GenericFakeChatModel`.**

Логику, специфичную для подкласса `ReasoningChatOpenAI` (парсинг reasoning-контента, пост-обработка ответа), тестируем **отдельным unit'ом на сконструированных `AIMessage`**, не прогоняя через фейк-модель в графе.

Программируемые `tool_calls` выше — это про **agent-LLM** (у ReAct-агента tool-calling реальный). Guard устроен проще, и его форму фейка сверка по коду уже закрыла.

### Форма фейка для guard: простой текстовый `content`

Распространённое ожидание — что guard берёт вердикт через structured output (tool-calling или нативный `response_format`). **По коду это не так.** `classifier.py:100` делает обычный `await self._llm.ainvoke(messages, ...)` и парсит `str(response.content).strip().upper()`, проверяя членство в `{CLEAN, SUSPICIOUS, INJECTION}` (`classifier.py:28`), с ретраями на невалидный контент.

Значит фейк guard-модели — это **простой текст**, без tool_calls и без JSON:

```python
fake_guard = GenericFakeChatModel(messages=iter([AIMessage(content="INJECTION")]))
```

Вопрос «structured output: tool-calling vs response_format» снят — ни то ни другое. Это упрощает дизайн guard-фейков.

---

## 3. Тестирование графа LangGraph

Официальные паттерны применяем 1:1.

- **Фабрика графа + свежий checkpointer в каждом тесте.** `create_graph()` → `compile(checkpointer=InMemorySaver())`. Никакого переиспользования между тестами — изоляция.
- **Прямой вызов ноды:** `compiled_graph.nodes["node_name"].invoke({...})` — тестируем одну ноду в отрыве, checkpointer при этом игнорируется. Идеально для add-time блоков (нода guard на входе).
- **Частичный прогон без реструктуризации графа:** `update_state(config, values, as_node="prev")` подставляет состояние «как после ноды prev», затем `invoke(None, config, interrupt_after="stop")` выполняет только нужный кусок.
- **HITL / interrupt:** компиляция с checkpointer, `interrupt(payload)` в ноде ставит граф на паузу, возобновление через `Command(resume=...)`.
- **Условные рёбра (роутинг guard):** фейк guard-модели отдаёт вердикт `INJECTION` → ассертим, что граф ушёл в ветку блокировки; отдаёт `CLEAN` → пошёл дальше. Вердикты — `CLEAN/SUSPICIOUS/INJECTION` (`backend/app/agent/security/types.py:48`); действия `block/warning/redact` — отдельный слой (маппинг `INJECTION→ERROR` и т.д.), его ветвление проверяется отдельно от самого вердикта. Так детерминированно покрывается всё ветвление, которое сейчас требует живого ключа.

---

## 4. Тестирование SSE-стрима

Разделяем на два уровня.

**Unit на трансформацию событий.** Гоняем `graph.astream_events(..., version="v3")` под фейк-моделью, собираем события в список, проверяем их типы, порядок, полноту. `v3` — актуальная версия протокола событий. Здесь проверяем именно наш маппер «событие графа → SSE-событие клиента».

**Integration на FastAPI-эндпоинт.** `httpx.AsyncClient` + `ASGITransport`, метод `.stream()`, парсинг SSE-фреймов (удобно через `httpx-sse`).

```python
async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
    async with client.stream("POST", "/chat", json={...}) as resp:
        async for line in resp.aiter_lines():
            ...
```

**Грабли:** синхронный `TestClient` **буферизует стрим** — для честной проверки потока нужен async-клиент. Проверяем: типы событий, порядок, корректное событие отмены/ошибки, и что `security_block` доезжает до клиента как отдельный тип события.

**Отмена по разрыву соединения (client disconnect).** Отдельный кейс сверх «событие отмены доезжает»: клиент оборвал соединение посреди стрима → граф должен быть отменён, а не доработать вхолостую, и ресурсы (checkpointer-сессия, генерация) освобождены. Путь отмены/`CancelledError`/disconnect — `backend/app/agent/runner.py`, `backend/app/services/agent_runner.py`, `backend/app/api/routes/messages.py`. Тест эмулирует ранний выход из `async for` / закрытие клиентского стрима и ассертит, что внутренняя задача получила отмену и корректно свернулась (нет утечки задач/соединений).

### Изоляция `app.state` в тестах

Agent- и guard-ресурсы (модель/фабрика, guard, checkpointer, store, prompt-provider) живут в `app.state`, наполняемом composition root в lifespan. Integration-тест не должен полагаться на реальный lifespan (он тянет сеть/БД/ключи) — ресурсы переопределяются фикстурой: либо точечно через `app.dependency_overrides`, либо сборкой `app.state` тестовыми двойниками до прогона. Это та же точка, что вариант (б) шва из §1: подменив провайдер модели в `app.state`, мы разом получаем фейк во всём приложении. Принцип — каждый тест стартует с известного, изолированного `app.state`, без протечек между прогонами.

---

## 5. Record / replay через VCR

Второй контур — для путей, где важно именно реальное поведение reasoning-модели на проводе (полный агентный прогон, запись в Knowledge Sphere).

**Как работает:** `VCR.py` + `pytest-recording`. Один раз гоняем тест с живым ключом (`--record-mode=once`), HTTP-обмен с `api.openai.com` пишется в YAML-кассету, дальше тесты replay'ят запись без сети и без ключа. Тест падает, если **изменился запрос** (промпт, модель, tool-схема) — это регрессионный сигнал на дрейф промптов. Работает на уровне HTTP, **ниже** нашего `ReasoningChatOpenAI`, поэтому захватывает реальное поведение reasoning-модели (включая reasoning-блоки) без адаптации подкласса.

**Минусы и предостережения:**
- кассеты надо генерить с живым ключом и коммитить;
- **streaming-ответы (SSE от OpenAI) пишутся как chunked-тело — кассеты крупные и капризные к матчингу**;
- **обязательна фильтрация `Authorization` / api-key** из YAML (по умолчанию VCR пишет секреты as-is) — иначе утечка в репозиторий;
- reasoning-модели недетерминированны — матчить по **запросу**, не по ответу; нужна нормализация матчинга и декомпрессия gzip.

**Баланс ролей:** ручные фейки — основа (~90% тестов: быстро, бесплатно, читаемо, не ломается от смены версии модели). VCR — точечно на 2–3 сквозных пути, где важен реальный wire-формат. Это не «или-или», а разделение: фейки выражают намерение («модель вернула BLOCK»), VCR даёт реалистичность.

---

## 6. Граница unit vs eval

Это два *разных инструмента* с разной частотой и разной природой. Смешивать нельзя.

**Детерминированные pytest-тесты** (CI-гейт, на каждый PR, без ключа) покрывают **логику кода вокруг модели**:
- логика графа — рёбра, роутинг, аккумуляция состояния, HITL-паузы/резюме;
- парсинг ответов и structured output;
- **ветвление guard на фиксированных вердиктах `CLEAN/SUSPICIOUS/INJECTION`** + отдельный слой действий `block/warning/redact`;
- трансформация SSE-событий;
- контракт checkpointer / store.

Здесь ответ модели — это *вход теста*, который мы фиксируем; проверяем *код вокруг*. Ассерт строгий, бинарный, мгновенный, дешёвый. Вопрос, на который отвечает тест: «не сломал ли я код».

**Eval-наборы** (Langfuse datasets + LLM-as-judge / `openevals` / `agentevals`, по расписанию или перед релизом промпта, с живым ключом) покрывают **качество ответов живой модели**:
- качество ответов агента;
- точность guard на реальных атаках (recall на jailbreak-корпусе, false-positive rate);
- качество fuzzy-patch в Knowledge Sphere.

Здесь ответ модели — это *то, что оцениваем*; он недетерминирован, `assert ==` не работает — нужен judge или метрики на датасете. Вопрос: «стала ли система отвечать лучше или хуже».

**Почему нельзя смешивать:** недетерминированный eval в CI-гейте → флаки и заблокированные мержи; логика, проверяемая только через живую модель → дорого, медленно, не изолирует баг кода от поведения модели.

**Guard конкретно** — идеальный кандидат на детерминированные тесты: инъектируем фейк guard-модели, отдающий каждый из трёх вердиктов `CLEAN/SUSPICIOUS/INJECTION`, проверяем ветвление кода и слой действий (`INJECTION`→блокировка, `SUSPICIOUS`→warning/redact, `CLEAN`→пропуск). Guard уже инъектируем (`LLMClassifier(llm=...)`), так что эти тесты пишутся без правок прода. Отдельный кейс — graceful degradation: при сбое модели guard деградирует в CLEAN (`guard.py:149`); фейк, бросающий исключение, детерминированно воспроизводит этот путь (раньше он возникал только из-за отсутствия ключа). Качество же самой классификации (ловит ли guard реальные атаки) — это eval, не unit.

Langfuse уже стоит для observability — естественно переиспользовать его datasets + experiments как eval-харнесс (offline-прогон по датасету + LLM-as-judge). Это отдельный пайплайн от pytest. Нужен ли eval-контур уже в feat-009 или это отдельная итерация — развилка для архитектора (eval требует датасетов и живого ключа в отдельном пайплайне, не в CI-гейте).

---

## 7. Checkpointer в тестах

- **`InMemorySaver` по умолчанию** (`langgraph.checkpoint.memory`) для всей логики — быстро, без БД, официально рекомендован.
- **Реальный `PostgresSaver` / `AsyncPostgresSaver`** (`langgraph-checkpoint-postgres`) — узким слоем интеграционных тестов, чтобы ловить то, что in-memory не покажет: сериализацию состояния, поведение store, миграции схемы checkpointer.

Не гоняем всю логику против PG — это медленно и не добавляет сигнала. Дефолт in-memory + малый PG-контур.

---

## 8. Свежие API-факты (LangChain/LangGraph, проверено июнь-2026)

- `GenericFakeChatModel(messages=iter([...]))` — `langchain_core.language_models.fake_chat_models`; поддерживает `tool_calls` и streaming; рекомендован официальной страницей Unit testing.
- `InMemorySaver` — `langgraph.checkpoint.memory`; `PostgresSaver` / `AsyncPostgresSaver` — пакет `langgraph-checkpoint-postgres`.
- Прямой вызов ноды: `compiled_graph.nodes["name"].invoke(state)` (минует checkpointer).
- Частичный прогон: `update_state(config, values, as_node="prev")` + `invoke(None, config, interrupt_after="stop")`.
- HITL: `interrupt(payload)` в ноде + возобновление `Command(resume=...)`.
- Стриминг событий: `astream_events(..., version="v3")`.
- VCR: `@pytest.mark.vcr()`, `--record-mode=once|rewrite`; обязательны `filter_headers` (вырезать auth) и декомпрессия gzip.
- Eval: `openevals` (`create_llm_as_judge`, `CORRECTNESS_PROMPT`), `agentevals` (trajectory) — open-source, работают с Langfuse и LangSmith; Langfuse datasets + experiments — отдельный SDK-харнесс для offline-прогона.

---

## Что это значит для нас

1. **Шов в значительной части уже есть.** `build_graph(model=...)` и `LLMClassifier(llm=...)` инъектируемы — логику графа и guard тестируем фейком **без правок прода**. Дотянуть остаётся одну точку — `GraphFactory` (рекомендуемый вариант — model-factory параметром). Это меньше и безопаснее, чем казалось из feat-006: «переписывания архитектуры» нет.
2. **Программируем против `BaseChatModel`, не против `ReasoningChatOpenAI`** — тогда `GenericFakeChatModel` встаёт в шов и даёт детерминированный прогон ReAct-петли через программируемые `tool_calls` (это про agent-LLM).
3. **Форма фейка guard — простой текст** (`AIMessage(content="INJECTION")`): сверено по коду, guard парсит `content`, не structured output. Вопрос tool-calling/`response_format` снят.
4. **Вердикты — `CLEAN/SUSPICIOUS/INJECTION`**; `block/warning/redact` — отдельный слой действий, тестируется отдельно от вердикта.
5. **Два контура подмены:** ручные фейки — основа (логика, ветвление guard, SSE-маппер); VCR record/replay — точечно на 2–3 сквозных пути ради реального wire-формата, с обязательной фильтрацией секретов.
6. **Unit и eval — разные инструменты.** Детерминированная обвязка и ветвление guard на фиксированных вердиктах → unit в CI. Качество ответов и точность guard на атаках → eval через Langfuse, отдельный пайплайн вне CI-гейта. Вводить ли eval-контур уже в feat-009 — решение архитектора.
7. **Checkpointer:** InMemorySaver по умолчанию, тонкий PG-контур для сериализации/store. Изоляция `app.state` между тестами — через override/тестовые двойники, не через реальный lifespan.

Развилки, которые надо снять на Фазе 1: как дотянуть шов в `GraphFactory` (а/б/в); ручные фейки vs VCR и их пропорция; in-memory vs PG checkpointer в тестах; нужен ли eval-контур в этой итерации.

---

## Источники

- Unit testing (fake models, InMemorySaver) — https://docs.langchain.com/oss/python/langchain/test/unit-testing
- LangGraph Test (ноды, partial execution, update_state/interrupt_after) — https://docs.langchain.com/oss/python/langgraph/test
- Checkpointer libraries (InMemory / SQLite / Postgres) — https://docs.langchain.com/oss/python/langgraph/checkpointers
- `GenericFakeChatModel` reference — https://reference.langchain.com/python/langchain-core/language_models/fake_chat_models/GenericFakeChatModel
- pytest-recording (PyPI) — https://pypi.org/project/pytest-recording/
- VCR.py docs — https://vcrpy.readthedocs.io/
- «Eliminating Flaky Tests: VCR tests for LLMs» (Anay Nayak) — https://anaynayak.medium.com/eliminating-flaky-tests-using-vcr-tests-for-llms-a3feabf90bc5 · репо https://github.com/anaynayak/llm-vcr-tests
- Simon Willison TIL (pytest-recording / VCR) — https://til.simonwillison.net/pytest/pytest-recording-vcr
- Langfuse Datasets & Experiments — https://langfuse.com/docs/evaluation/experiments/datasets
- Langfuse Evaluation overview — https://langfuse.com/docs/evaluation/overview
- Langfuse LLM-as-a-Judge — https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge
- openevals / agentevals — https://docs.langchain.com/langsmith/openevals
- Тест FastAPI SSE через StreamingResponse (SO) — https://stackoverflow.com/questions/76674857/test-fastapi-with-server-sent-events-sse-using-streamingresponse
