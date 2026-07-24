# Test Cases: feat-003 — Модели: cost-optimal + whitelist expansion / трек T1

Итерация конфигурационная: меняется состав LLM-моделей (`agent.yaml`, `security.yaml`, `pricing.yaml`), унифицируется reasoning-конфиг (deprecated `include_reasoning` → `reasoning: {effort, exclude}`), правится наследование `extra_body` в резолвере при scope-override. Кода за пределами `model_config_resolver.py` и `security/types.py` (поле `ReasoningOptions.exclude`) не меняется — остальное данные в YAML.

Кейсы страхуют новую фичу и фиксируют направленные инварианты. Ожидаемые изменения поведения, которые кейсы подтверждают: (1) main-дефолт стал `z-ai/glm-5.2`, whitelist — пять утверждённых моделей (с Grok 4.5 вместо гео-заблокированной Muse Spark), лёгкие роли — `deepseek/deepseek-v4-flash`; (2) все точки reasoning-конфига несут единую форму (`effort medium`, guard — `effort minimal`, везде `exclude: false`); (3) при scope-override модели без собственного `extra_body` наследуется reasoning-дефолт из `agent.yaml`; (4) каждая активная модель однозначно матчится ровно одной записью `pricing.yaml` (коллизия `glm-5` ↔ `glm-5.2` снята негативным lookahead).

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры** (применять, если итерация их касается): `📊` — проверка наблюдаемости (структура БД, метрики, Redis state, Langfuse); `🔴` — проверка реальных инъекций / атак / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `tests/<scope>/`); `*(регресс)*` — кейс страхует «поведение не сломалось» (отделяет регресс от проверки нового поведения).
- **run-log** (только у перепрогнанных кейсов) — строка-история флипов с причиной:
  `runs: r1 ✅ → r2 ❌ (после фикса review #3: регрессия инвалидации) → r3 ✅`.
  Один прогон — run-log не нужен. Перепрогон после правки кода обязателен (см. ре-верификацию).

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`/`make check-fe`/`make test`) — перепрогон всегда; ручные/UI-кейсы — перепрогон только затронутой области. Каждый перепрогон → запись в run-log.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики: не сошлось — повтори (мог быть транзиент); не сошлось второй раз — fail + эскалация, без долгой отладки. Инструменты: structlog (JSON stdout), Langfuse traces, состояние БД, Redis Streams (`XINFO`/`XLEN`). Код читать только там, где поведение иначе не наблюдаемо (явно отмечать). Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer** (A6: fixer ≠ автор теста), не сам тестировщик.

**Скоуп по трекам.** Кейсы с префиксом трека (`{T1.1}`) гоняются на своём треке + Layer 0; cross-cutting (Layer 2/3 без префикса) — в INTEGRATION_TEST (`{track_id}=final`). Не пропускать кейсы молча — неприменимый помечать причиной.

### Процесс (тестировщик поднимает стенд сам)

Итерация конфигурационная — офлайн-кейсы Layer 0/1 не требуют стенда (грузятся боевые YAML через `load_*_config()` без сети и БД). Живой стенд нужен только Layer 3 (👤 архитектора): переключение модели через UI, cost-атрибуция новых моделей в Langfuse на реальном трейсе, боевой guard. Боевые LLM-вызовы (`model_smoke.py`) платные — прогнаны оркестратором, перепрогону не подлежат.

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| Langfuse cost-атрибуция | Langfuse UI → trace → generations → cost |
| Смоук-результаты | [smoke-run-results.md](../../smoke-run-results.md) |

---

## Дизайн автотестов

**Покрываем автотестом** — по одной записи на суиту:

### `test_pricing_consistency.py` — консистентность pricing.yaml против активного набора моделей

1. **Файл**: `backend/tests/agent/test_pricing_consistency.py` — unit, без сети; шов — загрузка боевых YAML (`load_agent_config` / `load_security_config` / `load_pricing_config`) + regex.
2. **Тестирует**: `configs/pricing.yaml` против активного набора моделей из `configs/agent.yaml` и `configs/security.yaml`; `app.agent.config.load_pricing_config`, `ModelDefinitionConfig.match_pattern`.
3. **Суть**: гарантирует, что каждая модель, реально подключённая в конфиги (main, summarization, subagents, whitelist, guard), имеет ровно одну матчащую запись цен, — то есть Langfuse атрибутирует затраты однозначно, а price-drift-тест находит с чем сравнивать. Страхует от того, что кто-то добавит модель в whitelist и забудет цену, и от повторного возникновения коллизии паттернов уровня `glm-5` ↔ `glm-5.2`.
4. **Кейсы**: активный набор непуст (≥ 6 slug — sanity, чтобы ассерты не проходили вхолостую); все `match_pattern` компилируются; каждый активный slug матчится ровно одной записью (не 0, не >1).

### `test_pricing_external.py` — цены и доступность whitelist против живого каталога OpenRouter

1. **Файл**: `backend/tests/agent/test_pricing_external.py` — external (marker `external`, в дефолтном `make test`); шов — один `httpx.get {llm_base_url}/models` (публичный каталог, ключ не нужен).
2. **Тестирует**: `configs/pricing.yaml` (цены активных моделей) и `available_models` против `GET https://openrouter.ai/api/v1/models`.
3. **Суть**: ловит реальные репрайсинги и депрекейшны на OpenRouter — цены активных моделей не должны отклоняться от каталога больше чем на ±10% (допуск против внутридневных флуктуаций multi-provider агрегата), а каждая whitelist-модель должна существовать в каталоге, поддерживать `tools` и нести контекст ≥ 100k. Деградирует мягко: любая сетевая недоступность или не-200 → `pytest.skip` целого модуля, не fail (тест страхует данные, не достижимость).
4. **Кейсы**: price-drift активных моделей (`input`/`output`/`input_cache_read`, допуск 10%, fail с диффом); поле, отсутствующее в каталоге, пропускается только при нуле в yaml (кейс `stepfun/step-3.5-flash` без cache-цены); доступность пяти whitelist-моделей (в каталоге + `tools` + context ≥ 100k).

### `test_model_config_resolver.py` (новые кейсы наследования) — каскад extra_body при scope-override

1. **Файл**: `backend/tests/personalization/test_model_config_resolver.py` — sociable-unit, без БД; шов — `FakeSettingsRepo` (in-memory rows) + `StubPromptProvider`.
2. **Тестирует**: `app.services.model_config_resolver.ModelConfigResolver.resolve` / `._resolve_extra_body`.
3. **Суть**: фиксирует новое поведение наследования — когда scope (thread/project/user) переопределяет модель, но строка настроек не несёт собственного `extra_body` (пришёл `None` или сериализованный `{}`), резолвер подставляет reasoning-дефолт из `agent.yaml` `llm`, а не отдаёт пустой конфиг; при этом собственный непустой `extra_body` scope остаётся приоритетным. Страхует от регрессии дефекта, из-за которого при переключении модели терялся reasoning-конфиг. Регресс-кейсы (thread wins, каскад до project/user/langfuse/config) остаются в файле и подтверждают, что порядок каскада не сломан.
4. **Кейсы**: override с `extra_body=None` → унаследован дефолт; override с `extra_body={}` → унаследован дефолт; override со своим непустым `extra_body` → приоритет свой; (регресс) thread override wins с своим extra_body; (регресс) langfuse-config extra_body берётся из config-источника, не наследуется.

**Осознанно не покрываем автотестом** — триадами *(что — почему — куда уехало)*:

- Фактическое поведение моделей (ответ приходит; рассуждения — полные/суммаризованные/нет; usage с reasoning-токенами) — требует платных боевых LLM-вызовов, вне CI — → полуручной `model_smoke.py`, результат зафиксирован в [smoke-run-results.md](../../smoke-run-results.md), кейс `{T1.9}`.
- Отдаёт ли guard-модель `gemini-3.5-flash-lite` рассуждения при `effort minimal` (особый интерес архитектора) — тот же паттерн платного вызова — → смоук, кейс `{T1.9}` (закрыт: guard отдаёт полные рассуждения, латентность < 600 мс).
- Langfuse-атрибуция затрат по `match_pattern` на реальном трейсе (единственный рантайм-потребитель паттернов — сидер Langfuse) — нужен живой стенд + прогон агента + Langfuse — → Layer 3 `{final}` 👤 📊.
- Переключение модели пользователем через UI (thread/project/user scope) и сквозной проброс reasoning-конфига в боевой запрос — нужен браузер + БД + backend — → Layer 3 `{final}` 👤.
- Резолвер против реального `SettingsRepository` / Postgres — sociable-unit сознательно на фейках (контракт — резолвенная модель+источник, не lookups) — → Layer 3 e2e (UI switching) косвенно.

**Замеченные прод-баги (для fixer'а, сам не чиню):** нет.

### Layer 0: Automated gate

- [x] `make check` — ruff + mypy + import-linter (9 contracts KEPT) + arch-checker → **0 ошибок**. Только предсуществующие arch-checker `WARN` (file-size/dir-size на `main.py`, `mcp_servers.py`, `agent/`, `api/routes`, `api/schemas`, `services/`) — не связаны с правкой feat-003, это warnings, не errors.
- [x] `make test` — **753 passed** (backend) + **21 passed** (migrations) + **64 passed** (siem-contracts), 0 failed. external-тесты `test_pricing_external.py` реально прошли против живого каталога (не skip) — сеть доступна вне sandbox через `excludedCommands`.
- [x] Целевые суиты изолированно (`test_pricing_consistency.py` + `test_pricing_external.py` + `test_model_config_resolver.py`): **16 passed** (3 + 2 external PASSED + 11 резолвер).
- [x] Маркер `external` зарегистрирован в `backend/pyproject.toml` (`"external: hits third-party network APIs"`).

---

## Ручные кейсы + статусы

### Layer 1: Трек T1 — models-config (офлайн, без стенда и платных вызовов)

- [x] `{T1.1}` `load_agent_config()` → main = `z-ai/glm-5.2`; whitelist = пять записей (`z-ai/glm-5.2`/GLM-5.2, `google/gemini-3.6-flash`/Gemini 3.6 Flash, `deepseek/deepseek-v4-pro`/DeepSeek V4 Pro, `x-ai/grok-4.5`/Grok 4.5, `qwen/qwen3.7-max`/Qwen3.7 Max); summarization и subagents = `deepseek/deepseek-v4-flash`. **Результат**: совпало точь-в-точь; `extra_body` во всех трёх точках (llm/summarization/subagents) = `{'reasoning': {'effort': 'medium', 'exclude': False}}` — единая форма, `include_reasoning` из YAML убран. Whitelist несёт Grok 4.5 (не Muse Spark) — фикс-цикл применён.
- [x] `{T1.2}` `load_security_config()` → guard-модель **не изменилась** (`google/gemini-3.5-flash-lite`); `llm_classifier.extra_body.as_dict()` = `{'reasoning': {'effort': 'minimal', 'exclude': False}}`. **Результат**: подтверждено — guard остался на прежней модели, reasoning на `effort minimal` + `exclude: false`, детекторы/чекпойнты/messages не тронуты.
- [x] `{T1.3}` `ReasoningOptions.exclude` сериализуется корректно: `LLMExtraBody(reasoning=ReasoningOptions(effort='minimal', exclude=False)).as_dict()` эмитит `exclude: false`; при `exclude=None` (конфиг без поля) — опускается. **Результат**: `exclude=False` → `{'reasoning': {'effort': 'minimal', 'exclude': False}}`; `exclude=None` → `{'reasoning': {'effort': 'medium'}}`. Обратная совместимость (конфиги без `exclude`) сохранена.
- [x] `{T1.4}` `load_pricing_config()` парсится без ошибок; направленный инвариант «активные ⊆ pricing.yaml». **Результат**: 14 записей; 7 активных slug (glm-5.2, gemini-3.6-flash, deepseek-v4-pro, grok-4.5, qwen3.7-max, deepseek-v4-flash, gemini-3.5-flash-lite) — все имеют запись; ретеншн (`glm-5`, `glm-4.7-flash`, `gemini-3.1-pro-preview`, `gemini-3-flash-preview`) и альтернативы (`minimax-m2.5`, `tencent/hy3`, `stepfun/step-3.5-flash`) сохранены. Обратное включение не требуется — инвариант направленный. [auto: `test_pricing_consistency.py`]
- [x] `{T1.5}` Уникальность матча: каждый активный slug матчится ровно одной записью `pricing.yaml`; все 14 паттернов компилируются; коллизия `glm-5` ↔ `glm-5.2` снята. **Результат**: все 7 активных → ровно 1 матч (ALL UNIQUE: True); `z-ai/glm-5` → `['z-ai/glm-5']`, `z-ai/glm-5.2` → `['z-ai/glm-5.2']` (негативный lookahead `(?![.\d])` на ретеншн-записи работает, решение OQ#1 корректно). Все паттерны компилируются. [auto: `test_pricing_consistency.py`]
- [x] `{T1.6}` Наследование `extra_body` в резолвере: scope-override без своего `extra_body` (`None` или `{}`) наследует дефолт `agent.yaml`; собственный непустой — приоритетен; каскад/langfuse-ветка не сломаны. **Результат**: 11 кейсов `test_model_config_resolver.py` passed, включая три новых (None→дефолт, {}→дефолт, own→приоритет). [auto: `test_model_config_resolver.py`]
- [x] `{T1.7}` *(регресс)* Вне scope feat-003 не тронуто: `image.model` = `google/gemini-3.1-flash-image`; `context`/`subagents.registry`/`mcp_servers` на месте. **Результат**: `image.model` не изменился; секции присутствуют (verified диффом коммитов и загрузкой конфига).
- [x] `{T1.8}` *(регресс)* Env-гигиена: новых env-переменных нет, `app/config.py` / `.env*.example` / `docker-compose.yml` не тронуты feat-003. **Результат**: 7 code-коммитов feat-003 (`ab11329`…`fa57477`) касаются только `security/types.py`, `model_config_resolver.py`, `pyproject.toml`, тестов и трёх `configs/*.yaml` + docs. Env-surface — вне их скоупа (файлы в диффе `main...HEAD` — от несвязанных develop-коммитов).
- [x] `{T1.9}` 👤*(полуручной, платный — не перепрогонять)* Смоук боевого состава: 7 моделей (5 whitelist + deepseek-v4-flash + guard) отвечают с боевым reasoning-конфигом роли; классификация рассуждений и usage; особый интерес — отдаёт ли guard рассуждения. **Результат** (прогон оркестратора, [smoke-run-results.md](../../smoke-run-results.md)): **7/7 ответили**; guard `gemini-3.5-flash-lite` отдаёт **полные рассуждения** при `effort minimal`, латентность < 600 мс — **вопрос архитектора закрыт**. Grok 4.5 — суммаризованные (ожидаемо для xAI). GLM-5.2 — полные, reason-токены вошли в completion (для cost-учёта не критично: output и output_reasoning тарифицируются одинаково).

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [ ] Неприменимо: итерация не вводит межсервисных интеграционных швов (только данные-конфиги + чистый резолвер). Cost-атрибуция и UI — ниже в Layer 3.

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST) — требуют живого стенда, 👤 архитектора

- [ ] `{final}` 👤 Переключение модели через UI: зарегистрировать пользователя, в настройках переключить модель на каждую из пяти whitelist (thread- или user-scope), отправить сообщение, убедиться, что агент отвечает выбранной моделью. Проверить, что при переключении модели без явного `extra_body` в боевой запрос уходит reasoning-дефолт из `agent.yaml` (`effort medium, exclude false`) — смотреть Langfuse generation input или structlog запроса к OpenRouter.
- [ ] `{final}` 👤 📊 Cost-атрибуция в Langfuse на реальном трейсе: прогнать агент на новых моделях (main `glm-5.2` + переключение на whitelist), в Langfuse UI открыть generations трейса и проверить, что затраты атрибутируются корректной записью цен (`match_pattern` резолвится однозначно, cost > 0, не «unknown model»). Особое внимание — `glm-5.2` не должна ошибочно матчиться ретеншн-записью `glm-5`.
- [ ] `{final}` 👤 📊 Боевой guard на новом reasoning-конфиге: отправить сообщение, проходящее через guard-чекпойнт, убедиться, что вердикт приходит, `GuardResult.details.reasoning` заполнен (guard отдаёт рассуждения — подтверждено смоуком `{T1.9}`), латентность приемлема; guard-затраты атрибутируются записью `gemini-3.5-flash-lite`.

---

## Находки ревью [severity+owner]

> Пишет **test-reviewer** (adversarial-ревью тестов против контракта, read-only). Чисто — секция пустая.

- (пусто — заполняет test-reviewer)

---

## Покрытие

| Инвариант / риск из design-brief | Закрывающие кейсы |
|---|---|
| Состав моделей (main/whitelist/лёгкие роли) утверждён | `{T1.1}` |
| Guard-модель неизменна, единая reasoning-форма (minimal) | `{T1.2}`, `{T1.3}` |
| `include_reasoning` → `reasoning:{effort,exclude}` во всех точках | `{T1.1}`, `{T1.2}`, `{T1.3}` |
| Активные ⊆ pricing.yaml (направленный инвариант) | `{T1.4}` [auto] |
| Коллизии паттернов запрещены (OQ#1, lookahead) | `{T1.5}` [auto] |
| Наследование extra_body при scope-override | `{T1.6}` [auto] |
| Ретеншн-записи выбывших моделей сохранены | `{T1.4}` |
| Price-drift ±10% против живого каталога | Layer 0 external [auto] |
| Доступность whitelist (tools, context ≥ 100k) | Layer 0 external [auto] |
| Env-гигиена (нет новых env) | `{T1.8}` |
| Боевые ответы + guard reasoning | `{T1.9}` 👤 (смоук) |
| Cost-атрибуция Langfuse / UI switching | Layer 3 `{final}` 👤 |
