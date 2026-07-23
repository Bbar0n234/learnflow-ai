# Design Brief: feat-003 (D) — Модели: cost-optimal + whitelist expansion

Транскрипция решений архитектора, принятых в интерактивной сессии 2026-07-23 по итогам ресёрча ([research-candidates.md](research-candidates.md), методика — [doc/reference/model-selection.md](../../../../tech/../reference/model-selection.md)). Дизайн-развилок не осталось — все решения ниже утверждены явно.

## Утверждённый состав моделей

| Роль | Было | Становится |
|------|------|-----------|
| Main дефолт (`agent.yaml` → `llm.model`) | `z-ai/glm-5` | `z-ai/glm-5.2` |
| Whitelist (`available_models`) | GLM-5, GLM-4.7 Flash, Gemini 3.1 Pro | `z-ai/glm-5.2` (GLM-5.2), `google/gemini-3.6-flash` (Gemini 3.6 Flash), `deepseek/deepseek-v4-pro` (DeepSeek V4 Pro), `x-ai/grok-4.5` (Grok 4.5), `qwen/qwen3.7-max` (Qwen3.7 Max) |
| Summarization (`summarization.model`) | `z-ai/glm-4.7-flash` | `deepseek/deepseek-v4-flash` |
| Субагенты (`subagents.llm.model`) | `z-ai/glm-4.7-flash` | `deepseek/deepseek-v4-flash` |
| Guard (`security.yaml` → `llm_classifier.model`) | `google/gemini-3.5-flash-lite` | **без изменений** |
| Image (`image.model`) | `google/gemini-3.1-flash-image` | **вне scope** |

Отклонены архитектором: Kimi K3 (медленная, цена на грани), Gemini 3.1 Pro Preview в whitelist не остаётся; `meta/muse-spark-1.1` — гео-блок US-only единственного провайдера (вскрыто смоуком), заменена на Grok 4.5.

## Reasoning-конфиг (единая форма)

Deprecated `include_reasoning: true` заменяется унифицированным OpenRouter-параметром во всех точках конфига:

- `llm.extra_body`, `summarization.extra_body`, `subagents.llm.extra_body`: `reasoning: {effort: medium, exclude: false}` — **effort medium** (решение архитектора; на DeepSeek V4, поддерживающем только high/xhigh, OpenRouter замаппит на high — штатное поведение).
- Guard (`security.yaml` → `llm_classifier.extra_body`): `reasoning: {effort: minimal, exclude: false}` — guard должен оставаться быстрым (у `gemini-3.5-flash-lite` дефолт-effort minimal, reasoning mandatory); рассуждения возвращаются — их захват в `GuardResult.details.reasoning` уже реализован.

Обоснование безопасности единой формы: OpenRouter нормализует `reasoning.effort` между провайдерами (конвертация в token-budget / thinkingLevel), модели без reasoning молча игнорируют параметр — подтверждено доками (см. research-candidates.md § Reasoning-конфиг).

## Наследование extra_body при переключении модели

Дефект: каскад `ModelConfigResolver` (thread → project → user) при override модели берёт `extra_body` из scope-настройки, где он пуст, — reasoning-конфиг дефолта теряется. Решение текущей итерации (компромисс, полная per-scope конфигурация — в backlog): **если scope-override не несёт собственного `extra_body`, наследуется `extra_body` из `agent.yaml` `llm`** — единая reasoning-форма безопасна для всего whitelist. Реализация — в резолвере (`backend/app/services/model_config_resolver.py`), точное место выбирает planner.

## pricing.yaml

- **Добавить** (цены живые с OpenRouter, снапшот в [openrouter-catalog-snapshot.md](openrouter-catalog-snapshot.md); перед правкой перепроверить свежим `GET /api/v1/models`): `z-ai/glm-5.2`, `google/gemini-3.6-flash`, `deepseek/deepseek-v4-pro`, `x-ai/grok-4.5`, `qwen/qwen3.7-max`, `deepseek/deepseek-v4-flash` + утверждённые альтернативы карты ролей: `minimax/minimax-m2.5`, `tencent/hy3`, `stepfun/step-3.5-flash`.
- **Актуализировать** дрейфанувшие цены: `z-ai/glm-5` (0.95/2.55, cache 0.20), `z-ai/glm-4.7-flash` (0.06/0.40, cache 0.01).
- **Не удалять** записи моделей, выбывших из конфигов (`z-ai/glm-5`, `google/gemini-3.1-pro-preview`, `google/gemini-3-flash-preview`): сохранённые пользовательские overrides могут ссылаться на них — cost-учёт должен продолжать матчиться. Инвариант направленный: *все активные модели ⊆ pricing.yaml*, обратное включение не требуется.
- Паттерн записи — как существующие: `output_reasoning` = цена output, `match_pattern` — `(?i)^<slug с экранированием>`.
- **Коллизии паттернов запрещены** (решение архитектора по OQ#1 плана): каждый активный slug обязан матчиться ровно одной записью. Префиксные коллизии снимаются негативным lookahead: ретеншн-запись `z-ai/glm-5` получает `(?i)^z-ai/glm-5(?![.\d])`, новая `z-ai/glm-5.2` — `(?i)^z-ai/glm-5\.2`. Unit-тест консистентности дополняется assertion'ом уникальности матча.

## Тесты (состав утверждён архитектором)

1. **Unit, постоянный контур** — конфиг-консистентность: каждая модель из `agent.yaml` (llm, summarization, subagents.llm, все available_models) и `security.yaml` (guard) имеет запись в `pricing.yaml`, чей `match_pattern` компилируется и матчит slug. Без сети.
2. **External, постоянный контур** (marker `external`, входят в дефолтный `make test`): (а) price-drift — цены `pricing.yaml` (input/output/input_cache_read) против живого `GET https://openrouter.ai/api/v1/models`; **допуск ±10%** (решение архитектора: цены multi-provider моделей флуктуируют внутри дня как агрегат по провайдерам — жёсткое равенство флаки-по-данным; fail только при отклонении > 10%, что ловит реальные репрайсинги и игнорирует шум роутинга), расхождение сверх допуска → fail с диффом; (б) доступность whitelist — каждая whitelist-модель существует в каталоге, поддерживает tools, контекст ≥ 100k. **Семантика падений**: OpenRouter недоступен (timeout, 5xx, сетевая ошибка) → `pytest.skip` с причиной; данные расходятся сверх допуска → fail. Marker регистрируется в `backend/pyproject.toml` (`external: hits third-party network APIs`).
3. **Смоук-скрипт, полуручной** (артефакт итерации, НЕ в CI — платные LLM-вызовы): по каждой модели состава (5 whitelist + deepseek-v4-flash + guard) один короткий вызов через OpenRouter с боевым reasoning-конфигом роли; вывод-таблица: ответ получен / рассуждения вернулись (полные | суммаризованные | нет) / usage с reasoning-токенами. Особый интерес архитектора: **отдаёт ли guard-модель `gemini-3.5-flash-lite` рассуждения** (прецедент: GLM-4.7 Flash отдавала, Gemini 3.1 Flash Lite — нет). Ключ — `OPENROUTER_API_KEY`/`LLM_API_KEY` из `.env` (посмотреть фактическое имя в `Settings`).

## Известные следствия (приняты)

- Пользовательские overrides на выбывшие модели продолжают работать (резолвер не перевалидирует сохранённое); валидация whitelist действует на установку нового override.
- Price-drift-тест будет фейлить CI при дрейфе цен до правки `pricing.yaml` — осознанная forcing function (аналог устаревшего lockfile).
- Метки Preliminary на арене у части кандидатов — рейтинги могут осесть; валидация состава — догфудингом (runtime switching).

## Env-гигиена

Новых env-переменных нет: конфиги моделей — YAML, ключи не меняются. `Settings`/`.env.example`/`docker-compose.yml` не затрагиваются (проверить при ревью, что это так и осталось).

## Партиция треков

Один трек `T1` (models-config): объём мал, файловые скоупы связаны (конфиги ↔ тесты ↔ резолвер). Конвейер последовательный.

## SOFA consulted

Не выполнялся: итерация конфигурационная, паттернов уровня Blueprint не потребляет (ресёрч внешних бенчмарков — вне домена SOFA).
