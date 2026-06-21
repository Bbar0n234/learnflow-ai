# feat-009 · Testing — Philosophy + Coverage

Артефакты итерации. Статус на текущий момент: пройдена **Фаза 0** (discovery + теория),
на гейте **Фазы 1** (согласование развилок с архитектором).

## Как мы ведём feat-009

Итерация не ложится на стандартный конвейер оркестратора (результат — сама тестовая
инфраструктура и тесты, а не код против готовых test-cases; нужна параллельность). Ведём
кастомным фазовым workflow:

```
Ф0 Discovery + Theory   → Ф1 Philosophy/решения → conventions-first
   → Ф2 Shared infra (1 агент, замораживается)
   → Ф3 Parallel coverage (фан-аут по слайсам)
   → Ф4 Review → Ф5 «всё зелёное» → Ф6 встройка в workflow
```

Параллелим только после Фазы 2: общая инфра (фикстуры, фейк-LLM, тестовая БД) строится и
замораживается одним агентом, затем тестировщики пишут новые файлы в непересекающихся
слайсах.

## Документы

- [`theory/00-discovery.md`](theory/00-discovery.md) — текущее состояние (чистый лист) + вывод по skill-discovery.
- [`theory/01-philosophy.md`](theory/01-philosophy.md) — модели тестов, что тестируем по слоям, test doubles, антипаттерны, DoD.
- [`theory/02-python-engineering.md`](theory/02-python-engineering.md) — pytest/async, тестовая БД, фабрики, coverage.
- [`theory/03-llm-agent-testing.md`](theory/03-llm-agent-testing.md) — шов инъекции модели, фейки/VCR, тестирование графа и SSE, граница unit/eval.
- [`theory/04-frontend-testing.md`](theory/04-frontend-testing.md) — Vitest/RTL, MSW (+SSE), Playwright, Testing Trophy.
- [`decisions-phase1.md`](decisions-phase1.md) — **свод развилок Фазы 1** для разбора с архитектором.

## Ключевая находка Фазы 0

Главный фокус — проверяемость security-/agent-путей (боль из feat-006). Уточнение по коду: шов для
подмены модели **частично уже есть** — `build_graph(model=...)` (graph.py:193) и `LLMClassifier(llm=...)`
(classifier.py:34) принимают модель параметром, так что логику графа и guard можно тестировать фейком
**без правок прода**. Модель создаётся внутри только в `GraphFactory.build()` (graph_factory.py:52) и
в composition root — туда шов и дотягиваем (`decisions-phase1.md` § C1). Guard парсит простой текст
(`AIMessage(content="INJECTION")`), не structured output; вердикты — `CLEAN/SUSPICIOUS/INJECTION`.
