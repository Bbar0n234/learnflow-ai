# Implementation Plan: feat-003 (D) — Track T1 (models-config)

Реализация утверждённого состава моделей и reasoning-конфига по [design-brief](../../design-brief.md). Все дизайн-решения зафиксированы там; этот план — только декомпозиция на атомарные фазы для implementer'а. Данные цен и метаданных — [research-candidates.md](../../research-candidates.md) и [openrouter-catalog-snapshot.md](../../openrouter-catalog-snapshot.md).

**Трек один, конвейер последовательный.** Порядок фаз обязателен: конфиги-данные (1–3) кладут корректное состояние, резолвер (4) правит поведение, тесты (5) закрепляют инварианты по уже приведённому состоянию, смоук (6) — полуручной артефакт.

## Согласованные факты по коду (сверено с реализацией)

- `extra_body` в `agent.yaml` (`llm`, `summarization`, `subagents.llm`) — свободный `dict[str, Any]` (`app/agent/config.py:11-13,22-25`), новую форму `reasoning: {effort, exclude}` принимает как есть, без правки схемы.
- Guard читает `extra_body` через типизированную модель `LLMExtraBody` → `ReasoningOptions` (`app/agent/security/types.py:102-118`). Текущий `ReasoningOptions` знает только `effort`; поля `exclude` нет — чтобы боевой запрос нёс `reasoning.exclude: false`, поле надо добавить (Фаза 3). Без него pydantic молча отбросит `exclude` из YAML.
- Субагенты (`app/agent/subagents/runner.py:142-148`) и summarization (`app/infra/llm.py:111-121`) читают `extra_body` каждый из своей секции `agent.yaml` — правок кода не требуют, новую форму подхватят автоматически.
- Каскад `ModelConfigResolver.resolve` (`app/services/model_config_resolver.py:32-71`) при scope-override берёт `extra_body` строго из строки настроек scope; при пустом `extra_body` reasoning-дефолт теряется — это и есть дефект под Фазу 4.
- `match_pattern` из `pricing.yaml` потребляется только сидером Langfuse (`app/infra/langfuse.py:140`) — больше нигде в рантайме. Значит корректность паттернов проверяется через Langfuse-матчинг и через unit-тест консистентности, а не через рантайм-резолв.
- Ключ OpenRouter — `Settings.llm_api_key` (env `LLM_API_KEY`), base URL — `Settings.llm_base_url` (`https://openrouter.ai/api/v1`), `app/config.py:13-14`. Отдельного `OPENROUTER_API_KEY` в `Settings` нет.
- Маркеры pytest сейчас: `unit`, `integration`, `slow` (`backend/pyproject.toml:40-44`). `external` не зарегистрирован. `make test` фильтра по маркерам не ставит — прогоняет всё, значит `external` попадают в дефолтный прогон (соответствует brief § Тесты).
- Env-гигиена: новых env-переменных нет; `Settings`/`.env*`/`docker-compose.yml` не трогаем (brief § Env-гигиена).

---

## Фаза 1 — pricing.yaml: добавления, актуализация дрейфа, ретеншн

**Файл:** `configs/pricing.yaml`
**Схема:** правок в `app/agent/config.py` (`ModelDefinitionConfig`, `PricingConfig`) не требуется.

Перед правкой **перепроверить цены свежим `GET https://openrouter.ai/api/v1/models`** (brief § pricing.yaml); ниже — целевые значения из снапшота 2026-07-23, если каталог не дрейфнул. Все цены — per-token (`$/M × 1e-6`), `unit: TOKENS`, `output_reasoning` = `output`, паттерн `(?i)^<slug с экранированными точками>`.

**Добавить** (см. brief § pricing.yaml; цены из [snapshot](../../openrouter-catalog-snapshot.md)):

| slug | input | output / output_reasoning | input_cache_read |
|---|---|---|---|
| `z-ai/glm-5.2` | 7.8e-07 | 2.45e-06 | 1.448e-07 |
| `google/gemini-3.6-flash` | 1.5e-06 | 7.5e-06 | 1.5e-07 |
| `deepseek/deepseek-v4-pro` | 4.35e-07 | 8.7e-07 | 3.6e-09 |
| `meta/muse-spark-1.1` | 1.25e-06 | 4.25e-06 | 1.5e-07 |
| `qwen/qwen3.7-max` | 1.475e-06 | 4.42e-06 | 2.95e-07 |
| `deepseek/deepseek-v4-flash` | 9.8e-08 | 2.0e-07 | 1.96e-08 |
| `minimax/minimax-m2.5` | 1.5e-07 | 9.0e-07 | 5.0e-08 |
| `tencent/hy3` | 1.4e-07 | 5.8e-07 | 3.5e-08 |
| `stepfun/step-3.5-flash` | 1.0e-07 | 3.0e-07 | 0.0 |

Последние три (`minimax-m2.5`, `hy3`, `step-3.5-flash`) — утверждённые альтернативы карты ролей (brief), в `agent.yaml`/`security.yaml` не подключаются, но должны иметь цену на случай ручного свапа.

**Актуализировать дрейф** существующих записей:
- `z-ai/glm-5`: input `9.5e-07`, output/output_reasoning `2.55e-06`, input_cache_read `2.0e-07` (было `1.0e-06 / 3.2e-06 / 2.5e-07`).
- `z-ai/glm-4.7-flash`: input `6.0e-08`, output/output_reasoning `4.0e-07`, input_cache_read `1.0e-08` (было `1.25e-07 / 5.0e-07 / 3.125e-08`).

**Сохранить (не удалять)** записи выбывших из конфигов моделей — `z-ai/glm-5`, `google/gemini-3.1-pro-preview`, `google/gemini-3-flash-preview`: пользовательские overrides могут на них ссылаться, cost-учёт должен продолжать матчиться (brief). Инвариант направленный: активные ⊆ pricing.yaml.

**Коллизия паттернов (см. Open Questions #1).** Существующий паттерн `z-ai/glm-5` — `(?i)^z-ai/glm-5` — префиксно матчит новый активный slug `z-ai/glm-5.2` (проверено: `re.match` даёт True). Пока OQ#1 не решён, реализовать нельзя корректно: две записи (`glm-5` и `glm-5.2`) матчат один slug, Langfuse-атрибуция затрат становится неоднозначной. Рекомендация — сузить паттерн ретеншн-записи `glm-5` так, чтобы он не захватывал `5.2`/`5.1` (напр. `(?i)^z-ai/glm-5(?![.\d])`), новую запись `glm-5.2` дать как `(?i)^z-ai/glm-5\.2`. Финальную форму утверждает архитектор (OQ#1); от неё зависит и assertion уникальности в Фазе 5.

**Verification:**
- `python -c "from app.agent.config import load_pricing_config; load_pricing_config()"` (из `backend/`, через `uv run --package learnflow-backend`) — парсится без ошибок.
- Все `match_pattern` компилируются (`re.compile`) — покроется unit-тестом Фазы 5; здесь достаточно ручной проверки, что каждый активный slug матчится ровно одной записью с учётом решения OQ#1.
- `make check` — зелёный (правка YAML на ruff/mypy не влияет, прогон подтверждает отсутствие сопутствующего дрейфа).

---

## Фаза 2 — agent.yaml: состав моделей + единая reasoning-форма

**Файл:** `configs/agent.yaml`
**Схема:** правок не требуется.

По [brief § Утверждённый состав](../../design-brief.md) и § Reasoning-конфиг:

- `llm.model`: `z-ai/glm-5` → `z-ai/glm-5.2`.
- `llm.extra_body`: заменить `{include_reasoning: true, reasoning: {effort: low}}` на единую форму
  ```yaml
  extra_body:
    reasoning:
      effort: medium
      exclude: false
  ```
- `summarization.model`: `z-ai/glm-4.7-flash` → `deepseek/deepseek-v4-flash`; `summarization.extra_body`: `{include_reasoning: true}` → та же единая форма (`reasoning: {effort: medium, exclude: false}`).
- `subagents.llm.model`: `z-ai/glm-4.7-flash` → `deepseek/deepseek-v4-flash`; `subagents.llm.extra_body`: `{include_reasoning: true}` → та же единая форма.
- `available_models`: заменить текущие три записи на утверждённые пять (slug + display_name):
  - `z-ai/glm-5.2` → «GLM-5.2»
  - `google/gemini-3.6-flash` → «Gemini 3.6 Flash»
  - `deepseek/deepseek-v4-pro` → «DeepSeek V4 Pro»
  - `meta/muse-spark-1.1` → «Muse Spark 1.1»
  - `qwen/qwen3.7-max` → «Qwen3.7 Max»
- `image.model` — **не трогать** (brief: вне scope).

Замечание по effort medium: на GLM-5.2 и DeepSeek V4, поддерживающих только high/xhigh, OpenRouter замаппит medium на high — штатное поведение (brief § Reasoning-конфиг), правок не требует.

**Verification:**
- `python -c "from app.agent.config import load_agent_config; c=load_agent_config(); print(c.llm.model, [m.name for m in c.available_models])"` — main = `z-ai/glm-5.2`, whitelist = пять утверждённых slug.
- Существующий тест `tests/agent/test_config.py::test_load_real_configs_parse_into_typed_models` проходит.
- `make check` — зелёный.

---

## Фаза 3 — security.yaml: guard extra_body (единая форма, minimal) + `ReasoningOptions.exclude`

**Файлы:** `configs/security.yaml`, `backend/app/agent/security/types.py`.

По [brief § Reasoning-конфиг](../../design-brief.md): модель guard **не менять** (`google/gemini-3.5-flash-lite` остаётся), меняется только `extra_body`.

1. `app/agent/security/types.py` — добавить в `ReasoningOptions` поле `exclude`:
   ```python
   class ReasoningOptions(BaseModel):
       effort: str | None = None
       exclude: bool | None = None
   ```
   `LLMExtraBody.as_dict()` уже сериализует `reasoning` через `model_dump(exclude_none=True)` — `exclude: false` (не None) попадёт в payload корректно, `exclude: None` — опустится. Поле `include_reasoning` в модели оставить (default `False`, в payload не эмитится) — удаление не требуется и рискованно без нужды; brief требует убрать его только из YAML.

2. `configs/security.yaml` — `llm_classifier.extra_body`:
   ```yaml
   extra_body:
     reasoning:
       effort: minimal
       exclude: false
   ```
   (было `{include_reasoning: true}`). `effort: minimal` — guard остаётся быстрым; `exclude: false` — рассуждения возвращаются, их захват в `GuardResult.details.reasoning` уже реализован (brief).

**Verification:**
- `python -c "from app.agent.security.config import ...; from app.agent.security.types import LLMExtraBody, ReasoningOptions; print(LLMExtraBody(reasoning=ReasoningOptions(effort='minimal', exclude=False)).as_dict())"` → `{'reasoning': {'effort': 'minimal', 'exclude': False}}` (проверить фактический путь загрузчика security-конфига).
- Загрузка боевого `security.yaml` в типизированную модель без ошибок; `llm_classifier.model` остался `google/gemini-3.5-flash-lite`.
- Существующие тесты в `tests/security/` проходят; `make check` — зелёный.

---

## Фаза 4 — resolver: наследование extra_body при scope-override без собственного

**Файл:** `backend/app/services/model_config_resolver.py`

Дефект и решение — [brief § Наследование extra_body](../../design-brief.md): при override модели на уровне thread/project/user, если строка настроек **не несёт собственного `extra_body`**, наследуется `extra_body` из `agent.yaml` `llm` (единая reasoning-форма безопасна для всего whitelist).

Реализация:
- Ввести хелпер, который для каждого scope-hit возвращает `extra_body` строки, если он непустой, иначе — `self._llm_config.extra_body or None`. «Непустой» = не `None` и не пустой dict (`{}`), т.к. строки настроек хранят JSON и могут дать `{}`.
- Применить в трёх ветках (thread, project, user). Ветку Langfuse-config **не трогать** (там свой источник `extra_body`, наследование дефолта агента к нему не относится — сохранить текущее поведение). `default()` уже отдаёт `agent.yaml` `extra_body` — не менять.
- **Приоритет собственного `extra_body` scope сохраняется**: если пользователь явно сохранил `extra_body`, он остаётся приоритетным (наследование срабатывает только при пустом).

**Verification:**
- Существующие тесты `tests/personalization/test_model_config_resolver.py` проходят без изменений (они либо задают свой `extra_body`, либо не проверяют `extra_body` на ветках project/user).
- Новые unit-тесты (Фаза 5) фиксируют: (а) scope с моделью и без `extra_body` → унаследован `agent.yaml` `extra_body`; (б) scope с моделью и `{}` → унаследован; (в) scope со своим непустым `extra_body` → он и остаётся.
- `make check` — зелёный.

---

## Фаза 5 — тесты: unit-консистентность + external (drift/availability) + регистрация маркера

**Файлы:** `backend/pyproject.toml` (маркер), новый тест-модуль(и) в `backend/tests/` по существующим конвенциям (см. ниже), новые кейсы резолвера в `tests/personalization/test_model_config_resolver.py`.

Состав тестов — [brief § Тесты](../../design-brief.md) (ID кейсов не используем — test-cases.md авторит test-author позже).

**Конвенции проекта, которым следовать:**
- Маркеры через `@pytest.mark.<marker>` (см. `tests/agent/test_config.py`, `tests/personalization/test_model_config_resolver.py`).
- Конфиг-тесты грузят боевые конфиги через `load_agent_config()` / `load_pricing_config()` / загрузчик security (без сети) — образец `tests/agent/test_config.py::test_load_real_configs_parse_into_typed_models`.
- Резолвер-тесты — sociable-unit с `FakeSettingsRepo` / `StubPromptProvider` (образец в `tests/personalization/test_model_config_resolver.py`), без БД.
- Размещение: unit-консистентность — рядом с конфиг-тестами (`tests/agent/`); external — новый модуль (напр. `tests/agent/test_pricing_external.py`) с маркером `external`; кейсы резолвера — в существующий `test_model_config_resolver.py`.

**5a. Регистрация маркера** — `backend/pyproject.toml`, в `[tool.pytest.ini_options].markers` добавить строку `"external: hits third-party network APIs"` (brief).

**5b. Unit, постоянный контур — конфиг-консистентность (без сети):**
- Собрать множество активных моделей: `agent.yaml` — `llm.model`, `summarization.model`, `subagents.llm.model`, все `available_models[*].name`; `security.yaml` — `llm_classifier.model`.
- Для каждой: существует запись в `pricing.yaml`, чей `match_pattern` компилируется (`re.compile`) и матчит slug (`re.match`).
- **Уникальность матча** (форма зависит от OQ#1): среди записей `pricing.yaml` активный slug должен матчиться однозначно — либо ровно одной записью, либо, если архитектор оставит префиксные паттерны, тест фиксирует ожидаемую запись явным образом. Без решения OQ#1 assertion уникальности упадёт на `glm-5` vs `glm-5.2` — это forcing function, не баг теста.

**5c. External, постоянный контур (маркер `external`, в дефолтном `make test`):**
Общая семантика падений (brief): OpenRouter недоступен (timeout, 5xx, сетевая/DNS-ошибка) → `pytest.skip(reason=...)`; данные получены, но расходятся → `fail` с диффом. Реализовать через один запрос к `GET https://openrouter.ai/api/v1/models` (base URL/ключ — из `Settings`, env `LLM_API_KEY`; при отсутствии ключа для этого публичного эндпоинта ключ не обязателен, но использовать `Settings.llm_base_url` как источник хоста). Обернуть сетевой вызов в try/except на сетевые исключения → skip.
- **(а) price-drift:** цены `pricing.yaml` (`input` / `output` / `input_cache_read`) каждой **активной** модели против живого каталога; расхождение → fail с диффом (какая модель, какое поле, yaml vs live). Ретеншн-записи выбывших моделей от drift-проверки можно освободить (их в live-каталоге может уже не быть) — проверять только активный набор; отсутствие активной модели в каталоге ловит тест доступности (ниже).
- **(б) доступность whitelist:** каждая из пяти `available_models` существует в каталоге, поддерживает tools, контекст ≥ 100k; иначе fail.

**5d. Новые кейсы резолвера** (в `test_model_config_resolver.py`, маркер `unit`) — наследование extra_body из Фазы 4: пустой/`{}`/собственный непустой (см. Verification Фазы 4).

**Verification:**
- `make test` — зелёный. В sandbox external-тесты уйдут в `skip` (сеть `--unshare-net` недоступна) — это подтверждает корректность skip-семантики; вне sandbox (`make test` исполняется через `excludedCommands`) они реально бьют каталог.
- Unit-тесты (консистентность + резолвер) проходят офлайн.
- `make check` — зелёный.

---

## Фаза 6 — смоук-скрипт (полуручной, артефакт итерации)

**Новый файл:** standalone-скрипт в директории итерации, вне `backend/tests/` и вне CI (образец такого артефакта — `doc/tasks/iterations/post-mvp/feat-004-security/langfuse_security_experiment.py`). Предлагаемое имя: `doc/tasks/iterations/dogfooding/feat-003-model-selection/model_smoke.py`.

По [brief § Тесты п.3](../../design-brief.md): по каждой модели состава — 5 whitelist + `deepseek/deepseek-v4-flash` + guard (`google/gemini-3.5-flash-lite`) — один короткий боевой вызов через OpenRouter с reasoning-конфигом своей роли (whitelist/summarization/subagents → `effort medium`; guard → `effort minimal`, оба `exclude: false`). Ключ и base URL — из `Settings` (`LLM_API_KEY`, `llm_base_url`).

Вывод — таблица по каждой модели: ответ получен (да/нет); рассуждения вернулись (полные | суммаризованные | нет); usage с reasoning-токенами. **Особый интерес архитектора** (brief): отдаёт ли guard-модель `gemini-3.5-flash-lite` рассуждения при `effort minimal` (прецедент: GLM-4.7 Flash отдавала, Gemini 3.1 Flash Lite — нет). Скрипт печатает это явно.

Скрипт платный (боевые LLM-вызовы) — запускается вручную, не из `make test`/CI; в шапке — предупреждение и способ запуска.

**Verification:**
- Скрипт синтаксически корректен и проходит `make check`, если попадает под ruff-скоуп; если директория итерации вне линт-скоупа backend — проверить, что запуск `python model_smoke.py --help`/dry-run не падает на импортах.
- Фактический прогон против OpenRouter — полуручной, результат прикладывается к артефактам итерации архитектором (не гейт CI).

---

## Порядок и коммиты

Шесть атомарных фаз, каждая — отдельный осмысленный коммит с verification:

1. `configs/pricing.yaml` — состав цен (**блокируется OQ#1** в части паттерна `glm-5`).
2. `configs/agent.yaml` — состав моделей + reasoning medium.
3. `security.yaml` + `ReasoningOptions.exclude` — guard minimal.
4. `model_config_resolver.py` — наследование extra_body.
5. Тесты + маркер `external` (assertion уникальности в 5b **зависит от OQ#1**).
6. Смоук-скрипт (артефакт, вне CI).

---

## Open Questions

1. **Коллизия match_pattern `z-ai/glm-5` ↔ `z-ai/glm-5.2`.**
   - **Что:** ретеншн-запись `z-ai/glm-5` (сохраняется под legacy-overrides) имеет паттерн `(?i)^z-ai/glm-5`, который префиксно матчит новый активный slug `z-ai/glm-5.2` (подтверждено `re.match`). Обе записи (`glm-5`, `glm-5.2`) матчат один slug.
   - **Где:** `configs/pricing.yaml:3` (существующий паттерн `glm-5`); новый slug `z-ai/glm-5.2` добавляется в Фазе 1.
   - **Почему это вопрос к архитектору:** brief § pricing.yaml фиксирует форму паттерна как `(?i)^<slug с экранированием>` — эта форма коллизию не разрешает. Langfuse при нескольких матчащих определениях выбирает по своей внутренней политике (recency/priority) — атрибуция затрат `glm-5.2` становится недетерминированной. Это корректностный, а не косметический вопрос; решать его сам (менять форму паттерна) не могу — это правка утверждённой в brief конвенции.
   - **Варианты:** (а) сузить паттерн ретеншн-записи `glm-5` негативным lookahead — `(?i)^z-ai/glm-5(?![.\d])` — новую запись дать как `(?i)^z-ai/glm-5\.2` (рекомендация: сохраняет legacy-матчинг `glm-5`, снимает коллизию, не трогает остальные паттерны); (б) end-anchor `(?i)^z-ai/glm-5$` для ретеншн-записи (проще, но не переживёт возможных variant-суффиксов вида `:free`/`:nitro`, если такие когда-либо окажутся в overrides); (в) оставить как есть и положиться на политику Langfuse (не рекомендуется — недетерминированная атрибуция).
   - **Что нужно от архитектора:** выбор формы паттерна. От решения зависят Фаза 1 (запись цен) и Фаза 5b (assertion уникальности матча в unit-тесте консистентности — при варианте «в» её придётся ослабить до «≥1 матч», потеряв forcing function).
