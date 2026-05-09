# ADR-023: Two-Level Detection — Deterministic Detectors + LLM Classifier

## Статус

Принято

## Контекст

Guard pipeline Security 2.0 проверяет контент на 7 checkpoints, включая streaming-режим (per-chunk на FINAL_OUTPUT). Каждый checkpoint получает контент разной природы: user input, tool results, tool call arguments, streaming output, MCP metadata при добавлении сервера.

LLM-классификатор (Sec 1.0) эффективен на семантическом уровне — ловит парафраз, format-shift, описание реализации без точных имён. Но его стоимость и latency (1–3 сек per invocation) не позволяют гонять его на каждом streaming chunk (50–200 на обычный ответ LLM). Нужен дешёвый быстрый слой для exact/near-exact совпадений.

Research R2 (output-similarity-metric-research.md) систематически исследовал candidate-метрики: substring match, Levenshtein ratio, fuzzy matching, n-gram Jaccard, embedding similarity, cross-encoder reranker. Вопрос: какую комбинацию слоёв принять, чтобы покрыть и exact-match, и semantic/paraphrase, без лишних зависимостей и сложности?

## Рассмотренные варианты

### A: Только LLM classifier

Один классификатор на все случаи.

- **За:** ловит семантику, парафраз, format-shift
- **Против:** 1–3 сек на вызов — неприменим per-chunk в streaming. Стоимость × N checkpoints × N tool calls. На educational платформе latency критичен

### B: Только deterministic detectors

Substring-детекторы на curated lists идентификаторов.

- **За:** <1 ms, интерпретируемые, нулевая стоимость, применимы per-chunk
- **Против:** не ловят парафраз («я сохраняю заметки между сессиями при помощи встроенного инструмента мемоизации» — не содержит точных имён, но раскрывает реализацию). Red Team подтвердил: model адаптируется и обходит exact-match через format-shift

### C: Промежуточные similarity-метрики

Комбинации Levenshtein ratio, fuzzy matching, n-gram Jaccard, embedding similarity, cross-encoder — между pure substring и LLM.

- **За:** градиент confidence, теоретически лучше substring на near-matches
- **Против:** каждая метрика — отдельная зависимость и tuning surface. Levenshtein O(N²) на длинных ответах. Embedding model — external API call или self-hosted overhead. N-gram Jaccard чувствителен к tokenization. R2 показал: ни одна промежуточная метрика не даёт компенсирующей value сверх того, что уже дают substring (exact) и LLM classifier (semantic). Снижают интерпретируемость: вместо «matched tool X param Y» — «embedding similarity 0.73»

### D: Deterministic detectors + LLM classifier, complementary (выбрано)

Два слоя разной природы. Deterministic — дешёвые, быстрые, ловят exact/near-exact. LLM — semantic, ловит парафраз. Short-circuit: deterministic hit → classifier не вызывается.

## Решение

### Четыре deterministic детектора

| Детектор | Что ловит | Триггер | Применимость |
|----------|-----------|---------|--------------|
| Canary | HMAC-токен в content | 1 hit | Все 7 checkpoints |
| Unicode | Невидимые символы (Cf, Co, Cn) | 1 hit | INBOUND + add-time |
| Paired Tool-Identifier | Утечка схемы internal non-MCP tool (имя + ≥1 параметр) | ≥3 compromised tools | OUTBOUND (FINAL_OUTPUT, TOOL_CALL_ARG) |
| Fragment | Дословное цитирование PROTECTED prose | ≥2 unique matches (60-char windows) | USER_INPUT, TOOL_RESULT, FINAL_OUTPUT, TOOL_CALL_ARG |

**Paired logic:** инструмент compromised при одновременной утечке имени И хотя бы одного параметра. Одиночные совпадения коротких param-имён (`query`, `url`) — шум, пропускаются. Registry содержит только internal non-MCP инструменты (PROTECTED boundary, ADR-022). MCP-имена в registry не попадают.

**Fragment detector:** sliding windows 60 chars (stride 30). Corpus — PROTECTED стабильные источники: hardening preamble, security instructions, base system prompt prose, skills content, descriptions internal non-MCP tools. Исключены: MCP descriptions (DISCLOSABLE), user-owned content. Minimum 2 unique matches — околонулевая вероятность случайного совпадения 7–10 слов подряд.

Нормализация для всех substring-детекторов: lowercase + `_-` → `_` + whitespace collapse.

### Один LLM classifier (composite prompt)

Единственный Langfuse-промпт `security-classifier` для всех 7 checkpoints. Checkpoint-специфика передаётся через переменные `checkpoint_description` / `checkpoint_specifics_section` / `history_section` / `content`. Один промпт вместо семи — единая точка поддержки, калибровки и rollback.

### Принципы взаимодействия слоёв

- **Short-circuit:** deterministic hit → classifier не вызывается. Действие уже выполнено, ресурсы не тратятся
- **Classifier isolation:** classifier prompt ничего не знает про deterministic-детекторы и «другие слои» защиты. Lightweight guard LLM, осведомлённая о наличии других слоёв, получает психологическое оправдание снижать бдительность — FN rate растёт
- **Единое действие:** любой слой генерирует verdict → единая механика redaction per checkpoint. Источник детекта пишется в метаданные для Langfuse traces и eval
- **Fail-open:** guard LLM exception / invalid response после retries → `graceful_degradation → CLEAN` + WARNING log (унаследовано из ADR-017)

### Конфигурируемость

Пороги и параметры детекторов вынесены в `security.yaml → detectors` (`paired.min_compromised_tools`, `fragment.window_size`, `fragment.stride`, `fragment.min_unique_matches`). Поддерживается override на конкретном checkpoint через `security.yaml → checkpoints.<name>.detectors.*` — двухуровневый merge (base → checkpoint). Applicability matrix (какой детектор на каком checkpoint работает) — compile-time инвариант в коде, через конфиг не меняется.

## Обоснование

- **Complementary, не redundant:** deterministic ловит exact-match (имена, параметры, цитаты prompt'а) — быстро, дёшево, интерпретируемо. LLM classifier ловит semantic leak (парафраз, description without names, format-shift). Каждый закрывает слепую зону другого.
- **Per-chunk feasible:** deterministic <1 ms на cumulative буфере. LLM classifier только end-of-stream — 1–3 сек на полном ответе, терпимо для educational платформы.
- **Промежуточные metrics отвергнуты:** R2 показал, что Levenshtein / fuzzy / n-gram / embedding не дают компенсирующей accuracy между substring и LLM. Каждая — дополнительная зависимость, tuning surface и снижение интерпретируемости. Substring + LLM покрывают оба полюса (exact ↔ semantic) без промежуточного слоя.
- **Composite prompt вместо семи:** семь отдельных prompts дублируют общую логику (роль, формат вердикта, taxonomy угроз). Переменные `checkpoint_description` / `checkpoint_specifics` дают ту же выразительность при одной точке поддержки.

## Следствия

- **Corpus assembly на startup:** Fragment detector собирает corpus из PROTECTED источников при инициализации и кэширует на инстансе. При обновлении prompt/skills — нужен restart.
- **FP risk analysis:**
  - Canary: ~0 (per-session HMAC, 32+ chars)
  - Paired (≥3 tools + ≥1 param): low — единственный реалистичный сценарий «доклад про Learnflow AI»
  - Fragment (≥2 × 60 chars): low–medium для слабых моделей в задаче «напиши system prompt»
- **Detectors package** (`app/agent/security/detectors/`) — четыре реализации `DeterministicDetector` Protocol с `applies_to: set[Checkpoint]`. Compile-time инвариант — регистрация при инициализации `SecurityGuard`.
- `normalize()` — shared helper для всех substring-детекторов.

## Связанные документы

- [research/security/output-similarity-metric-research.md](../../research/security/output-similarity-metric-research.md) — R2: candidate-метрики, thresholds, industry benchmarks
- [security/architecture.md](../../security/architecture.md) — detectors table, applicability matrix
- [ADR-022](./ADR-022-protected-disclosable-boundary.md) — PROTECTED corpus, registry scope
- [ADR-017](./ADR-017-prompt-injection-defense.md) — Sec 1.0: fail-open, sync guard
- [feat-006 design-brief](../../tasks/iterations/post-mvp/feat-006-security-2.0/design-brief.md) — §3.5 (two-level defense), §6.3 (detectors), §6.4 (composite classifier)
