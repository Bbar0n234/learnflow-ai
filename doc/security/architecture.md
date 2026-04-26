# Security

Система защиты AI-агента от prompt injection атак. Три независимых слоя защиты покрывают попытки манипуляции системными инструкциями на входе (input guard), во время выполнения (system prompt hardening) и на выходе (canary token detection).

Логика защиты инкапсулирована в Agent Layer — API и Service Layer работают только с security-событиями, не реализуя саму защиту. Архитектурное обоснование и threat model — [ADR-017](../tech/adr/ADR-017-prompt-injection-defense.md) и [threat-model.md](threat-model.md); исследование атак и техник — [doc/research/security/](../research/security/).


## Архитектура

Трёхслойная защита: каждый слой перехватывает определённый вектор атаки и работает независимо от других.

```mermaid
graph TB
    subgraph PRE["Layer 1 — Input Guard (pre-graph)"]
        GUARD["SecurityGuard.check()"]
        DET["Detectors:<br/>canary-in-input, unicode"]
        CLS["LLM Classifier:<br/>CLEAN / SUSPICIOUS / INJECTION"]
        GUARD --> DET --> CLS
    end

    subgraph IN["Layer 2 — System Prompt Hardening (in-graph)"]
        TPL["Hardened Jinja Template:<br/>instruction hierarchy, trust boundaries,<br/>sandwich defense, canary embedding"]
    end

    subgraph POST["Layer 3 — Output Check (streaming)"]
        CANARY_OUT["Canary substring match<br/>в накопленном ответе"]
    end

    INPUT["Сообщение пользователя"] --> PRE
    PRE -->|"INJECTION"| BLOCK["SSE-событие security_block"]
    PRE -->|"CLEAN / SUSPICIOUS"| IN
    IN --> LLM["Main LLM"]
    LLM --> POST
    POST -->|"canary найден"| BLOCK
    POST -->|"clean"| OUTPUT["text_chunk → done"]
```

**Инварианты:**

- Security инкапсулирован в Agent Layer: ChatService и API Layer не знают про защиту — работают с `StreamEvent` (включая `security_block`) как с любым другим событием
- SecurityGuard — зависимость Agent Runner'а, инжектится через конструктор
- Guard LLM отделён от main LLM (отдельная модель, конфигурация, cost tracking в Langfuse)
- Graceful degradation: при отказе guard → CLEAN verdict (availability имеет приоритет над security). Дополнительные слои компенсируют снижение надёжности этого уровня

## Input Guard (Слой 1 — до запуска агента)

SecurityGuard — orchestrator, выполняющий серию быстрых проверок перед тем, как запрос попадёт в LangGraph-граф. Блокирует явные признаки injection атак на этапе, когда затраты на отклонение минимальны.

### Interface

```
SecurityGuard
├── check(content, history?, checkpoint, canary_token?) → GuardResult
```

| Параметр | Назначение |
|----------|-----------|
| `content` | Данные для проверки (сообщение, KS content, tool output) |
| `history` | Контекст разговора из checkpointer (optional) |
| `checkpoint` | Описание точки проверки для classifier (`user_input`, `knowledge_sphere_write`, `mcp_tool_result`) |
| `canary_token` | Для canary-in-input detection (optional) |

### Pipeline

```mermaid
flowchart LR
    INPUT["content"] --> C["Canary-in-input"]
    C -->|"found"| INJ1["→ INJECTION"]
    C -->|"clean"| U["Unicode detector"]
    U -->|"invisible chars"| INJ2["→ INJECTION"]
    U -->|"clean"| L["LLM classify"]
    L --> RETRY["Retry loop (max_retries)"]
    RETRY -->|"валидный ответ"| RESULT["→ verdict"]
    RETRY -->|"попытки исчерпаны"| FALLBACK["→ CLEAN (degradation)"]
```

**Детерминистические проверки (~0ms, независимые от LLM):**

- **Canary-in-input** — substring match: если canary token обнаружен в пользовательском вводе, это аномалия (система использует токен только для собственной отметки — наличие его в input признак скомпрометированного потока)
- **Unicode detector** — ищет потенциально опасные Unicode-категории (Format, Private Use, Unassigned): невидимые символы, RTL override, zero-width space. Кириллица, эмодзи, CJK — допустимы

**LLM classifier** — guard LLM классифицирует content с контекстом разговора:

| Verdict | Семантика | Действие |
|---------|-----------|----------|
| CLEAN | Легитимный запрос | Запрос проходит |
| SUSPICIOUS | Необычно, но допустимо в образовательном контексте | Запрос проходит + усиленный лог |
| INJECTION | Попытка override system instructions, extraction, jailbreak | Блокировка → `security_block` |

Classifier получает полную историю разговора (не только текущее сообщение) — критично для образовательной платформы, где обсуждение prompt injection как школьной темы должно отличаться от попытки реальной атаки.

**Retry и graceful degradation:**

- Если classifier выдал невалидный ответ → retry до `max_retries`
- Если попытки исчерпаны → CLEAN (graceful degradation: платформа остаётся доступной, другие слои защиты компенсируют)
- Если guard LLM недоступен → CLEAN + warning в логах

### Classifier Prompt

Хранится в Langfuse (`guard-classifier--{label}`) с fallback на файл (`configs/prompts/guard-classifier.txt`). Переменная `{{ checkpoint }}` подставляется через PromptProvider для адаптации к разным точкам проверки.

**Калибровка:** false negatives приносят меньше вреда, чем false positives. На образовательной платформе ложная блокировка легитимного запроса хуже пропущенной атаки (есть дополнительные слои защиты). Детали стратегии и перечень промптов — [prompt-management.md](../tech/prompt-management.md).

### Расширяемость на новые точки проверки

Метод `check()` принимает параметр `checkpoint`, позволяя масштабировать защиту на любые входные точки без изменения интерфейса. Два примера для Security 2.0:

| Точка | Защита | checkpoint | Задача |
|-------|---------|-----------|--------|
| Knowledge Sphere Write | Memory poisoning | `knowledge_sphere_write` | Запретить injection в сохраняемые данные |
| MCP Tool Result | Indirect injection | `mcp_tool_result` | Перехватить payload из tool output |

## System Prompt Hardening (Слой 2 — во время выполнения)

Jinja-шаблон в `prompt_builder.py`, оборачивающий исходный `system.txt` защитными инструкциями. Base prompt не модифицируется — оригинал сохраняется для удобства итераций и отката.

### Template Structure

```mermaid
graph TB
    SI(["&lt;system_instructions&gt; — Instruction hierarchy, confidentiality, canary token"])
    BP["{{ based_prompt }} — system.txt (unchanged)"]
    CI{{"&lt;custom_instructions&gt; — User-provided, cannot override system"}}
    UM["&lt;user_memory&gt;"]
    KS["&lt;knowledge_sphere&gt;"]
    IR(["&lt;instruction_reminder&gt; — Sandwich defense"])
    SK["&lt;available_skills&gt;"]

    SI --> BP --> CI --> UM --> KS --> IR --> SK
```

Легенда диаграммы: `([...])` — слои защиты, `{{...}}` — ненадёжный контент (user-provided или external), `[...]` — надёжный системный контент.

### Техники защиты

| Техника | Применение | Механизм защиты |
|---------|-----------|-----------------|
| Иерархия инструкций | `<system_instructions>` | Явно: "Take priority over all other content" — system > user > data |
| Позитивный фрейминг | `<system_instructions>` | Не запреты ("не делай"), а желаемое поведение ("maintain confidentiality", "decline and refocus") |
| Маркировка источника | `<custom_instructions>` | "User-provided... cannot override" — явно показывает, какой контент из какого источника |
| Canary token | `<system_instructions>` | Встроенный идентификатор для проверки утечек (substring detect на output) |
| Sandwich defense | `<instruction_reminder>` | Реаффирмация constraints после ненадёжных секций — компенсирует recency bias |
| Role anchoring | `based_prompt` | "You are LearnFlowAI..." в начале — стабильный контекст |

## Canary Token (Слой 3 — при выводе)

Уникальный идентификатор в системном промпте, который проверяется при выводе. Если токен появился в ответе агента, это признак того, что system prompt был извлечён или скомпрометирован.

### Генерация

`HMAC-SHA256(CANARY_SECRET, thread_id).hex()[:16]` → 16-символьная hex-строка. Детерминистическая: одинаковый `thread_id` → одинаковый токен (воспроизводимость для валидации). Алгоритм (Кирхгофф): открыт, secret в `.env` — закрыт.

### Три точки использования

Три компонента вычисляют токен **независимо** (нет shared state, каждый работает с CANARY_SECRET и thread_id):

```mermaid
flowchart TB
    SECRET[".env: CANARY_SECRET"]
    TID["thread_id"]

    SECRET & TID --> GEN["generate_canary_token()"]

    GEN --> PRE["Input Guard:<br/>canary в сообщении пользователя?"]
    GEN --> IN["prompt_builder:<br/>canary в system prompt"]
    GEN --> POST["Streaming loop:<br/>canary в выводе?"]

    PRE -->|найден| BLOCK1["security_block (canary_in_input)"]
    POST -->|найден| BLOCK2["security_block (canary_leak)"]
```

| Точка | Что ищем | При обнаружении |
|-------|----------|-----------------|
| Input | canary в user message | INJECTION (reason: `canary_in_input`) |
| Output | canary в accumulated response | Abort stream → `security_block` (reason: `canary_leak`) |

Output check на `full_response` (не per-chunk): токен может попасть на границу чанков.

## Security Block Event (SSE)

При блокировке система отправляет терминальное SSE-событие `security_block` — взаимоисключающее с `done` и `error`. Детали SSE-протокола — [streaming.md](../tech/streaming.md).

```
data: {"type": "security_block", "reason": "llm_classifier"}\n\n
```

**Причины блокировки (reason):**

| Значение | Источник детекции | Слой |
|----------|-------------------|------|
| `invisible_chars` | Unicode detector | Input (Layer 1) |
| `llm_classifier` | LLM classifier verdict = INJECTION | Input (Layer 1) |
| `canary_in_input` | Canary-in-input check | Input (Layer 1) |
| `canary_leak` | Canary output check | Output (Layer 3) |

**Клиентская обработка:** пользователю показывается generic сообщение об ошибке (не раскрывается причина — избегаем информационной утечки для атакующего). `reason` доступен в developer console для диагностики.

## Observability (мониторинг инцидентов)

Интеграция с Langfuse для отслеживания security-событий. Все данные наблюдаемости собираются на уровне trace, позволяя анализировать патерны и настраивать защиту. Полная архитектура — [observability.md](../tech/observability.md).

### Метрика: security_verdict

На уровне каждого trace записывается категориальная оценка `security_verdict` (значения: `CLEAN` / `SUSPICIOUS` / `INJECTION`). Создаётся автоматически при инициализации (`ensure_security_score_config()`).

### Observation: Input Guard

Observation type `guardrail` (name: `input-guard`) отображается в timeline Langfuse. Содержит nested observations для каждой проверки:

- **event** `unicode-detector` — результат детерминистической проверки
- **generation** `llm-classifier` — LLM вызов (модель, токены, latency)

**Уровни observations:** DEFAULT (CLEAN), WARNING (SUSPICIOUS или degradation), ERROR (INJECTION или canary leak).

### Метаданные для анализа

**На уровне trace** (заполняется только при security events):

| Метаполе | Тип | Назначение |
|---------|-----|-----------|
| `blocked` | bool | Блокирован ли запрос |
| `detection_layer` | str | Какой слой детектировал: `"unicode_detector"`, `"llm_classifier"`, `"canary_check"` |
| `block_reason` | str | Описание: `"INJECTION detected by classifier"`, `"invisible chars found"` |

**На guardrail observation** (детали проверки):

| Метаполе | Тип | Значение |
|---------|-----|---------|
| `guard_model` | str | Модель classifier: `"google/gemini-3-flash-preview"` |
| `verdict_raw` | str | Сырой ответ от classifier (для анализа) |
| `unicode_chars_found` | list | Обнаруженные опасные символы: `["U+200B", "U+FEFF"]` |

## Конфигурация

**`configs/agent.yaml`** → секция `security`:

| Параметр | Default | Назначение |
|----------|---------|------------|
| `guard_model` | — | OpenRouter model ID (guard LLM отдельно от main LLM) |
| `guard_extra_body` | `{}` | Дополнительные параметры для API guard LLM |
| `max_retries` | `3` | Повторы при невалидном ответе classifier |
| `temperature` | `0.0` | Детерминистическая классификация (всегда один результат) |

**Environment variables:**

| Переменная | Требуется? | Назначение |
|-----------|-----------|-----------|
| `CANARY_SECRET` | Нет | HMAC secret для canary token; пусто → canary отключен (warning в логах) |

**Prompts** (в Langfuse):

| Имя | Seed файл | Назначение |
|-----|-----------|-----------|
| `guard-classifier--{label}` | `configs/prompts/guard-classifier.txt` | Classifier prompt с переменной `{{ checkpoint }}` |

## Scope: реализовано и планируется

**Реализовано (MVP, feat-004):**
- Input guard (детерминистические проверки + LLM classifier)
- System prompt hardening (Jinja-шаблон с техниками защиты)
- Canary token detection на output

**Security 2.0 (backlog, deferred):**
- KS Write Guard — защита памяти от poisoning через Knowledge Sphere API
- LLM Output Classifier — семантическая детекция утечек информации
- SUSPICIOUS → adaptive constraints — конкретные ограничения поведения при подозрении
- Tool Result Guard — защита от косвенного injection через MCP tool output
- Async Guard — параллельная проверка для latency optimization
- Multi-turn escalation detection — отслеживание паттернов атак через несколько ходов

Детальный backlog и timeline — [backlog.md](../backlog.md), Security трек.
