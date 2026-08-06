# Ф5a — кросс-скоуп фиксы инфры (packages/testing, Makefile)

Строго аддитивные правки тест-харнесса под находки adversarial-ревью: ни один
существующий тест не сломан, новые возможности добавлены рядом. Усиление самих
тестов под эти возможности — Ф5c (не здесь).

## Числа до/после (additivity gate)

| Гейт | До | После |
|------|----|-------|
| backend `make test` | 518 passed, 1 xfailed | 520 passed, 1 xfailed (+2 = новый Redis-canary) |
| siem-service | 46 passed | 46 passed |
| siem-contracts | 64 passed (вне гейта) | 64 passed (**в гейте**) |
| `make test-fe` | 78 passed | 78 passed (не трогал фронт) |
| `make check` | RED (преекзистинг format-дрейф в `test_knowledge_sphere_tools.py`) | GREEN |

Дельта backend +2 — ровно два новых canary-теста Redis-фикстуры; ни один
существующий тест не покраснел → аддитивность подтверждена.

## Что сделано

### 1. StubGuard (`packages/testing/learnflow_testing/fakes.py`) — S2 MAJOR-1/2, S6 M1, S7
- Новый kwarg `StubGuard(verdict, *, detection_layer: DetectionLayer | None = None)`;
  прокидывается в `GuardResult.detection_layer`. Теперь INJECTION с непустым слоем
  представим (прод всегда ставит слой) → ветки `block_reason`/`original_detection_layer`/
  `reason == "llm_classifier"` достижимы.
- Новое поле `call_records: list[dict]` — ПОЛНЫЕ аргументы каждого `.check()`
  (`content, checkpoint, history, canary_token, skip_classifier, observe, trace_ctx`).
  Позволяет утверждать mid-stream-контракт (`skip_classifier=True, observe=False` на
  `FINAL_OUTPUT`).
- Существующее `.calls: list[tuple[str, Checkpoint]]` оставлено ВЕРБАТИМ (на него
  опираются S2/S6) — `detection_layer` default `None`, поведение по умолчанию прежнее.

### 2. bind_tools-шов (`fakes.py`) — S3 кросс-скоуп
- Новый класс `ToolBindingFakeChatModel(GenericFakeChatModel)` с рабочим
  `bind_tools(tools, **kwargs) -> self` (no-op: схемы тулов реплей-фейку не нужны).
- `fake_chat_model([...])` теперь возвращает `ToolBindingFakeChatModel` → рекламируемый
  шов `GraphFactory(model_factory=model_factory(fake))` реально драйвит граф
  (`build_graph` зовёт `model.bind_tools`). Сигнатура и реплей-поведение неизменны.
- `_RaisingModel` переведён на `ToolBindingFakeChatModel`; добавлен публичный
  `raising_chat_model()` — tool-aware фейк, чей `ainvoke` бросает (model-failure ветка
  через граф). `raising_classifier_model()` сохранён без изменений.

Локальный `ToolBindingFakeChatModel` в `backend/tests/agent/conftest.py` оставлен как
есть (аддитивность; Ф5c может мигрировать на харнесс-версию).

### 3. Redis-фикстура (`packages/testing/learnflow_testing/plugin.py`) — S8 trace_store-блокер
По образцу Postgres-фикстуры:
- `redis_container` (session-scoped) — `RedisContainer("redis:7-alpine")`, образ под
  docker-compose; один контейнер на сессию (под xdist — на воркер).
- `redis_url` (session) — `redis://host:port/0`.
- `redis_client` (function-scoped, async) — `redis.asyncio.Redis`, `flushdb()` до и
  после теста (per-test изоляция, аналог транзакционного отката Postgres). Доступна и
  backend-, и siem-тестам (cross-project plugin).
- Canary: `backend/tests/chat/test_trace_store_redis.py` (2 теста, marker `integration`)
  — фикстура поднимается, `TraceStore` round-trip + изоляция. Полное покрытие
  `TraceStore` (TTL/feedback/batch) — Ф5c/S8.

Зависимости `packages/testing/pyproject.toml`: `testcontainers[postgres,redis]`,
`redis>=5.0`. `uv lock` обновлён.

### 4. Makefile — siem-contracts в гейт (S8-блокер)
- Новая цель `test-contracts` (`uv run --package siem-contracts pytest ... packages/siem-contracts/tests`).
- `test` и `test-parallel` теперь зовут `test-contracts` третьим шагом. `.PHONY` обновлён.

## Env
Новых env-переменных НЕТ: Redis URL берётся из testcontainer'а через фикстуру, не из
`Settings`/`.env`. Правок Settings/примеров/docker-compose не требуется.

## Дрейф-фикс (на месте)
`backend/tests/sphere/test_knowledge_sphere_tools.py` — преекзистинг format-дрейф
(коммит до моей работы валил `make check`). Применён `ruff format` — чисто
форматирование (схлопывание многострочных вызовов), без правок ассертов/поведения.

## Как этим пользоваться (Ф5c)
- **StubGuard:** `StubGuard(Verdict.INJECTION, detection_layer=DetectionLayer.LLM_CLASSIFIER)`
  → ассертить `reason == "llm_classifier"` (S6 M1, S7). Mid-stream-контракт:
  `guard.call_records[-1]["skip_classifier"] is True` и `["observe"] is False` (S2 MAJOR-2).
- **Граф через шов:** `fake_chat_model([...])` теперь проходит `build_graph`/`GraphFactory`
  напрямую; локальный `tool_binding_fake` больше не обязателен. Сбой апстрима —
  `raising_chat_model()`.
- **Redis:** запросить фикстуру `redis_client` (или `redis_url`), `TraceStore(redis_client)`.

## Где аддитивность недостижима
Нет таких мест. Все правки прошли без падения существующих тестов. Единственная правка
вне `packages/testing`/Makefile/новый-canary — format-дрейф в чужом тест-файле (только
форматирование, не ассерты), вынесен выше как drift-fix.
