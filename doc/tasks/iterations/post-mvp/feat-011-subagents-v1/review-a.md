## Code Review Report — режим A (качество кода)

### Summary
- blocker: 0 / nit: 2 / pre-existing: 0
- Плюс 1 замечание с намерением `question` (behavioral security, не блокер).

Вычитан весь diff (`git diff develop...HEAD`) построчно в контексте файлов и системы:
исполняющее ядро (`subagents/runner.py`, `subagents/graph.py`), tool (`tools/subagents.py`),
рефактор guard-хелперов (`tool_guards.py` + `graph.py`), wiring (`main.py`), стрим-фильтр
(`runner.py`), конфиги и все шесть тест-модулей. Логических ошибок, утечек ресурсов,
проглоченных исключений, регрессий для существующих вызывающих — не найдено.

Проверено отдельно и **признано корректным** (не выношу в замечания):
- Рефактор guard'ов в `tool_guards.py` — перенос дословный; `agent_node` (`graph.py:132-236`)
  вызывает те же функции, что и субагентский `_build_react_graph` (`subagents/graph.py:99-134`),
  порядок шагов и remap redacted-`ToolMessage` по `id` идентичны основному графу.
- Fetch артефактов «всё или ничего» (`tools/subagents.py:61-101`): сессия закрывается через
  `async with`, при любом проблемном id — `([], error)`, Runner не вызывается (тест
  `test_foreign_project_artifact_fails_the_whole_call`, `test_nonexistent_artifact_id_fails_without_running`).
- Инвариант анти-рекурсии: `pool.pop(RUN_SUBAGENT_TOOL_NAME, None)` в `__init__`
  (`subagents/runner.py:135`) безусловен; тест `test_run_subagent_is_excluded_from_the_tool_pool`.
- Стрим-фильтр по тегу (`runner.py:178-188`) — `continue` до аккумуляции `full_response` и
  canary-проверок; `cancel_event` проверяется выше по циклу, отмена остаётся отзывчивой.
- `dict(default_llm.extra_body) or None` (`subagents/runner.py:156`) — не падает: `extra_body`
  дефолтится в `{}` (не `None`), `dict({})` → `{}` → `None`. Ок.
- `.format(id=…, title=…)` применяется к шаблону-обёртке, не к значениям — фигурные скобки
  в `title`/`content` безопасны; кавычки экранируются `_escape_attr` (id и title).
- Fail-fast `_validate_subagent_tool_pool` агрегирует все проблемные спеки; двойная сборка
  guard'а в `main.py` — обоснована последовательностью зависимостей, `classifier`/`observer`
  переиспользуются.
- Тесты падают на реальной поломке: `test_stream_isolation` собирает `full_response`
  из смешанного потока и ассертит отсутствие `LEAKED_*`; guard-тесты в `test_graph.py`
  проверяют реакцию на вердикт (redact/strip), а не качество классификации.

### Замечания

| Severity | Намерение | Файл:строка | Замечание (со свидетельством поведения) | Предложение |
|---|---|---|---|---|
| nit | question | `backend/app/agent/subagents/graph.py:99-134` (`_build_react_graph.llm_node`) | Субагентский ReAct-цикл **не** применяет `compose_for_llm` (trust-boundary wrapping), которое основной граф применяет к `ToolMessage` перед вызовом модели (`graph.py:226`). Для `web-research` результаты firecrawl (недоверенные страницы) попадают в модель без делимитеров `<tool_output>…`; единственный in-cycle контроль — редакция guard'а при `TOOL_RESULT==INJECTION` (`tool_guards.py:88`). Контент с вердиктом `SUSPICIOUS`/`CLEAN`, но манипулятивный, доходит до модели «сырым», тогда как в основном графе он был бы хотя бы обёрнут trust-границей. Это задокументировано как намеренное (docstring `subagents/graph.py:18-24`, design-brief § «Безопасность»), поэтому не блокер — но это реальное снижение defense-in-depth относительно основного графа, и стоит явного подтверждения архитектора, что отказ от обёртки tool-результатов внутри цикла (а не только от KS/memory-секций системного промпта) — сознательный выбор. | Подтвердить намеренность; если да — оставить как есть (guard-редакция — компенсирующий контроль). Опционально: обернуть только mid-loop `ToolMessage` через `wrap_tool_output`, не трогая чистоту входного `HumanMessage`. |
| nit | suggestion | `backend/tests/subagents/test_run_subagent_tool.py:14` | В англоязычной docstring вклинена русская фраза: «…reaches the LLM, the **болезненная граница**, and is covered…». Смешение языков в docstring (CLAUDE.md § «Язык документации» — не смешивать; остальной код-контур англоязычный). Поведение не затронуто, чистая читаемость. | Заменить на англ. эквивалент, напр. «the sensitive boundary». |

Замечаний уровня blocker нет.
