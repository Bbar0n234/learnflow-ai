# Post-implementation Summary: feat-003 — трек T1

## Решения и обоснования

### Фаза 1 — pricing.yaml

- Добавлено 9 записей (5 whitelist + `deepseek/deepseek-v4-flash` + альтернативы `minimax/minimax-m2.5`, `tencent/hy3`, `stepfun/step-3.5-flash`), актуализирован дрейф `z-ai/glm-5` и `z-ai/glm-4.7-flash`, ретеншн-записи сохранены. Итог — 14 записей.
- OQ#1 (решение архитектора): ретеншн `z-ai/glm-5` → `(?i)^z-ai/glm-5(?![.\d])`, новая `z-ai/glm-5.2` → `(?i)^z-ai/glm-5\.2`. Проверено: каждый из 7 активных slug матчится ровно одной из 14 записей; все паттерны компилируются.
- Цены при правке перепроверены живым каталогом (`GET /api/v1/models`, 200 OK) — каталог дрейфанул от снапшота плана в пределах дня; использованы живые значения: `z-ai/glm-5.2` input 8.246e-07 (план 7.8e-07), output 2.5916e-06 (план 2.45e-06), cache 1.5314e-07; `deepseek/deepseek-v4-pro` cache 3.625e-09; `qwen/qwen3.7-max` output 4.425e-06; `deepseek/deepseek-v4-flash` output 1.96e-07. Остальные совпали с планом. `stepfun/step-3.5-flash` не поддерживает prompt caching (каталог не отдаёт `input_cache_read`) — плейсхолдер 0.0.
- Ретеншн-записи `google/gemini-3.1-pro-preview`, `google/gemini-3-flash-preview` по цене не актуализировались — вне мандата фазы (см. Follow-ups).
- Verification: `load_pricing_config()` → 14 моделей; `make check` зелёный (предсуществующие arch-checker warnings не связаны с правкой).

### Фаза 2 — agent.yaml: состав моделей + единая reasoning-форма

`configs/agent.yaml` приведён к утверждённому составу: main `z-ai/glm-5.2`; summarization и subagents — `deepseek/deepseek-v4-flash`; whitelist `available_models` — пять записей (GLM-5.2, Gemini 3.6 Flash, DeepSeek V4 Pro, Muse Spark 1.1, Qwen3.7 Max). Deprecated `include_reasoning: true` заменён во всех трёх точках (`llm`, `summarization`, `subagents.llm`) на единую форму `extra_body.reasoning: {effort: medium, exclude: false}`. Схема `app/agent/config.py` не менялась — `extra_body` там свободный `dict[str, Any]`. `image.model`, `context`, `subagents.registry`, `mcp_servers` не тронуты (проверено диффом). Verification: `load_agent_config()` отдаёт ожидаемые main/whitelist; `tests/agent/test_config.py` — 8 passed; `make check` зелёный.

### Фаза 3 — security.yaml + `ReasoningOptions.exclude`

`ReasoningOptions.exclude` добавлено опциональным полем (`bool | None = None`) — обратная совместимость сохранена: конфиги без `exclude` парсятся (`exclude=None`, `model_dump(exclude_none=True)` опускает его из payload). `configs/security.yaml` → guard на единой reasoning-форме (`effort: minimal, exclude: false`); сериализация подтверждена фактическим `as_dict()`: `{'reasoning': {'effort': 'minimal', 'exclude': False}}`. Модель guard и секции `detectors`/`checkpoints`/`messages` не менялись. `include_reasoning` в `LLMExtraBody` оставлен (план: удаление рискованно без нужды). Verification: `tests/security/` — 147 passed; `make check` зелёный.

### Фаза 4 — resolver: наследование extra_body

В `model_config_resolver.py` добавлен хелпер `_resolve_extra_body`: scope-override (thread/project/user) сохраняет приоритет своего `extra_body` только если он непустой; при `None`/`{}` подставляется дефолт из `agent.yaml` `llm` (`self._llm_config.extra_body or None` — тот же паттерн, что в `_from_llm_config`; truthiness dict эквивалентна «не пустой»). Применён в трёх ветках `resolve()`; ветка Langfuse-config и `default()` не тронуты (свой источник extra_body). Verification: `test_model_config_resolver.py` — 8 passed без правок; `tests/personalization/` — 128 passed; `make check` зелёный.

### Фаза 5 — тесты: unit-консистентность + external + маркер + кейсы резолвера

- 5a: маркер `external: hits third-party network APIs` в `backend/pyproject.toml`.
- 5b: `tests/agent/test_pricing_consistency.py` — активные модели (agent.yaml + security.yaml) ⊆ pricing.yaml; все паттерны компилируются; каждый активный slug матчится ровно одной записью (строгий assertion по решению OQ#1).
- 5c: `tests/agent/test_pricing_external.py` (маркер `external`) — один `GET {llm_base_url}/models`; сеть недоступна/не-200 → skip; price-drift активных моделей с допуском ±10% (решение архитектора) и диффом в fail-сообщении; поле, которого нет в каталоге, пропускается только при 0 в yaml (кейс `stepfun/step-3.5-flash`); доступность пяти whitelist-моделей (в каталоге, tools, контекст ≥ 100k).
- 5d: +3 кейса наследования extra_body в `test_model_config_resolver.py` (None → дефолт; `{}` → дефолт; собственный непустой → приоритетен).
- Прогоны: `tests/agent/ + tests/personalization/` — 227 passed; `make test` — 753 passed (external реально прошли против живого каталога, не skip); `make check` зелёный. Skip-ветка синтаксически корректна, но не форсировалась изоляцией сети (проверяется подстановкой недоступного base_url).

## Follow-ups

- **[P3, drift]** Ретеншн-записи `google/gemini-3.1-pro-preview` и `google/gemini-3-flash-preview` не синхронизированы с живым каталогом по цене — обновить при следующем пересмотре или включить в drift-скоуп, если архитектор решит.
- **[naблюдение для Фазы 5]** Цены multi-provider open-weights моделей в каталоге OpenRouter флуктуируют внутри дня (агрегат по провайдерам) — жёсткое равенство в price-drift тесте будет флаки-по-данным; семантика допуска — вопрос архитектору (эскалирован оркестратором).
