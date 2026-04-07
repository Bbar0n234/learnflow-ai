# Langfuse Observability: Security — решения по результатам экспериментов

## Контекст

Open question Q4 из [design-brief.md](design-brief.md): какую комбинацию механизмов Langfuse использовать для security observability — scores, tags, metadata, observation types.

**Метод:** standalone скрипт (`scripts/langfuse_security_experiment.py`, temporary), 6 сценариев (CLEAN, unicode INJECTION, SUSPICIOUS, LLM INJECTION, canary leak, guard failure), оценка визуального представления и фильтрации в Langfuse Cloud UI.

## Решения

### Score: `security_verdict` (CATEGORICAL)

Единый dimension для всех блокировок — и input guard, и output check.

| Значение | Семантика |
|----------|-----------|
| `CLEAN` | Угроз не обнаружено |
| `SUSPICIOUS` | Подозрительно, но не блокируем (образовательный контекст, пограничные случаи) |
| `INJECTION` | Блокировка — обнаружена инъекция или утечка |

- **Уровень:** trace (не observation) — один вердикт на весь запрос
- **Score config:** создаётся в lifespan при старте приложения (аналогично существующему `user-feedback`)
- **Canary leak:** verdict = INJECTION. Input guard мог дать CLEAN, но если output check обнаружил утечку — финальный verdict перезаписывается

### Observation type: `guardrail`

Input guard оформляется как observation с `as_type="guardrail"` (`name="input-guard"`).

Вложенная структура:

```
Guardrail "input-guard"
├── Event "unicode-detector"
└── Generation "llm-classifier" (если unicode прошёл)
```

- **Визуально:** иконка щита в trace timeline, отделяет security check от бизнес-логики
- **Аналитика:** фильтрация по observation type в Metrics API и custom dashboards
- **Latency/cost:** встроенные метрики Langfuse по observation name (percentiles из коробки, отдельный score не нужен)

### Metadata на trace (при инцидентах)

Проставляется на root span только при блокировке или degradation:

| Ключ | Значения | Назначение |
|------|----------|------------|
| `blocked` | `true` | Факт блокировки |
| `detection_layer` | `input_guard` / `output_check` | На каком слое сработала защита |
| `block_reason` | `unicode` / `llm_classifier` / `canary_leak` | Конкретная причина блокировки |
| `degraded` | `true` | Guard LLM упал, сработал graceful degradation |
| `error` | текст ошибки | Описание сбоя (только при degradation) |

### Metadata на guardrail observation

Диагностические детали для расследования конкретного trace:

| Ключ | Назначение |
|------|------------|
| `block_reason` | Причина блокировки (дублирует trace metadata для удобства drill-down) |
| `unicode_chars_found` | Список обнаруженных символов (только при unicode detection) |
| `guard_model` | Модель LLM-классификатора |
| `verdict_raw` | Сырой ответ классификатора (для отладки) |
| `degraded`, `error` | При graceful degradation |

### Observation levels

| Ситуация | Level | Обоснование |
|----------|-------|-------------|
| CLEAN | DEFAULT | Норма |
| SUSPICIOUS | WARNING | Подозрительно, но система продолжила работу |
| INJECTION (блокировка) | ERROR | Инцидент, пользователь заблокирован |
| Canary leak | ERROR | Инцидент, утечка системной информации |
| Guard LLM failure (degradation) | WARNING | Система справилась через fallback (availability > security) |

Семантика следует [conventions.md](../../../../tech/conventions.md#logging-conventions): WARNING = система справилась, но что-то не так; ERROR = операция провалилась, пользователь пострадал.

### Output trace

- **Нормальный flow:** текстовый ответ агента
- **Блокировка input guard:** `"Запрос заблокирован из соображений безопасности."`
- **Canary leak:** `"Ответ заблокирован: обнаружена потенциальная утечка системной информации."`
- **Degradation:** текстовый ответ агента (flow продолжился)

Diagnostic details (blocked, reason) — в metadata, не в output. Output = то, что видит пользователь.

## Отвергнутые варианты

| Вариант | Причина отказа |
|---------|---------------|
| **Tags** (`security-blocked`, `canary-leak`) | Дублируют score `security_verdict` + metadata `block_reason`. Фильтрация через score покрывает те же потребности. Tags оставлены свободными под будущие потребности (не обязательно security) |
| **NUMERIC score `guard_latency_ms`** | Latency по observation name — встроенная метрика Langfuse с percentiles (p50/p90/p95/p99). Отдельный score избыточен |
| **BOOLEAN score `security_blocked`** | Дублирует `security_verdict = INJECTION`. Один categorical score покрывает оба сценария (blocked / not blocked + granularity) |
| **Tag `security-suspicious`** | Не инцидент. Фильтруется через score `security_verdict = SUSPICIOUS` |

## Аналитика в Langfuse UI

| Потребность | Как закрыта |
|-------------|-------------|
| "Покажи все заблокированные traces" | Traces table → + Filter → Score `security_verdict` = `INJECTION` |
| "Покажи suspicious traces" | Traces table → + Filter → Score `security_verdict` = `SUSPICIOUS` |
| Distribution (сколько CLEAN / SUSPICIOUS / INJECTION) | Scores analytics → выбрать `security_verdict` → distribution |
| Trend over time | Scores analytics → выбрать `security_verdict` → trend |
| Pie chart (пропорции визуально) | Custom dashboard → widget: source `Scores - Categorical`, metric `Count`, dimension `Score Value`, filter `security_verdict`, chart type `Pie` |
| Guard latency percentiles | Dashboards → Latency → фильтр по observation name `input-guard` |
| "На каком слое сработала защита?" | Открыть заблокированный trace → metadata: `detection_layer`, `block_reason` |
| "Что увидел классификатор?" | Открыть trace → guardrail observation → metadata: `verdict_raw`, `guard_model` |

**Ограничение:** Langfuse custom dashboards не вычисляют ratio в одном виджете. "% заблокированных" как число — через Metrics API или два виджета рядом (INJECTION count + total count). Pie chart покрывает визуальную потребность.

## Расширяемость (Security 2.0)

При добавлении новых слоёв защиты (KS Write Guard, Tool Result Guard) — score и структура trace не меняются:

| Новый слой | `detection_layer` | `block_reason` |
|------------|-------------------|----------------|
| KS Write Guard | `ks_write` | `ks_injection` |
| Tool Result Guard | `tool_result` | `tool_injection` |
| LLM Output Classifier | `output_check` | `semantic_leak` |

`security_verdict` остаётся единым dimension: CLEAN / SUSPICIOUS / INJECTION. Новые слои добавляют значения в metadata, не в score.
