# ADR-017: Prompt Injection Defense Architecture

## Статус

Принято

## Контекст

LearnFlowAI — AI-агент для подготовки образовательных материалов. Агент имеет доступ к инструментам (MCP, Knowledge Sphere CRUD, artifacts), принимает пользовательский ввод и custom instructions. Поверхность атаки: direct prompt injection через user input, system prompt extraction, indirect PI через tool results и KS content.

Проект участвует в учебном Red Team / Blue Team формате (репозиторий open-source, принцип Кирхгоффа). MVP scope ограничен — часть векторов сознательно оставлена открытой.

Threat model: [security/threat-model.md](../../security/threat-model.md). Архитектурный ресёрч: [research/security/llm-defense-architecture-research.md](../../research/security/llm-defense-architecture-research.md).

Ключевые вопросы при проектировании:

1. **Sync vs async guard** — блокировать ли стрим до завершения проверки?
2. **Контекст для classifier** — текущее сообщение vs full history?
3. **Hardening** — переписать system prompt vs обернуть?
4. **Fail mode** — fail-open (availability) vs fail-closed (security)?

## Рассмотренные варианты

### 1. Sync vs Async Guard

**A: Sync guard (выбрано)** — проверка блокирует до начала стрима.

- За: простая архитектура, детерминированное поведение, INJECTION блокируется до любого side effect
- Против: +200-500ms к TTFT (time to first token)

**B: Async guard** — проверка параллельно с main LLM.

- За: нулевой impact на TTFT
- Против: shared events, race conditions (что делать, если guard вернул INJECTION после того, как LLM уже начал tool calls?); сложный cleanup; partial output уже у клиента

**Решение:** Sync. Latency +200-500ms терпима для образовательной платформы (не real-time chat). Async guard требует механик, несоразмерных MVP scope.

### 2. Контекст для LLM Classifier

**A: Только текущее сообщение.**

- За: минимум токенов, простота
- Против: false positives на образовательной платформе ("напиши доклад про prompt injection" → FP)

**B: Full conversation history (выбрано).**

- За: classifier видит контекст, различает обсуждение темы PI от реальной атаки
- Против: больше токенов, выше cost per check

**Решение:** Full history. Precision > recall: на образовательной платформе ложная блокировка легитимного пользователя неприемлема. Дешёвая guard-модель компенсирует рост cost.

### 3. System Prompt Hardening

**A: Переписать system.txt** — встроить hardening прямо в base prompt.

- За: один файл, всё в одном месте
- Против: hardening и content смешиваются; обновление base prompt рискует сломать hardening; сложнее поддерживать

**B: Jinja-обёртка (выбрано)** — hardening в template, system.txt подставляется как `{{ based_prompt }}`.

- За: separation of concerns (hardening vs content); system.txt итерируется независимо; hardening-секции (`<system_instructions>`, `<instruction_reminder>`) структурированы отдельно
- Против: два уровня абстракции (template + content)

**Решение:** Обёртка. system.txt не меняется — hardening добавляется без риска для существующего поведения агента.

### 4. Fail Mode

**A: Fail-closed** — guard недоступен → блокировать запрос.

- За: максимальная безопасность
- Против: guard LLM failure = полный outage для пользователя; single point of failure

**B: Fail-open (выбрано)** — guard недоступен → CLEAN verdict, запрос проходит.

- За: availability; guard — дополнительный слой, не единственный (hardening + canary работают независимо)
- Против: окно уязвимости при отказе guard

**Решение:** Fail-open. Availability > security для MVP. Два других слоя (hardening, canary) работают без guard LLM. Warning в логах обеспечивает observability деградации.

## Дополнительные решения

| Решение | Обоснование |
|---------|-------------|
| Отдельный guard LLM | Изоляция: своя модель, конфигурация, cost tracking. Дешёвая быстрая модель (не main LLM) |
| Три уровня verdict (CLEAN / SUSPICIOUS / INJECTION) | Гранулярность для мониторинга: SUSPICIOUS → усиленный лог (MVP), конкретные ограничения (Security 2.0) |
| Canary token — HMAC, no storage | Оба потребителя (prompt_builder, streaming loop) вычисляют независимо. Нет shared state |
| `security_block` — отдельный SSE terminal event | Frontend показывает специфичный UI, не generic error. Разделение security incidents от application errors |
| Checkpoint parameter для classifier | Контекст проверки в промпте. Масштабируется на KS write, tool results без изменения интерфейса |

## Последствия

**Положительные:**

- Layered defense: каждый слой покрывает свой вектор, отказ одного не обнуляет остальные
- Минимальный coupling: security инкапсулирован в Agent Layer, API/Service не затронуты
- Extensible: новые checkpoint'ы (KS, tools) через тот же `check()` интерфейс
- Observable: security incidents видны в Langfuse (scores, guardrail observations, metadata)

**Отрицательные:**

- +200-500ms latency на каждый запрос (sync guard)
- Runner усложнился: ~90 строк Langfuse observability кода (tech debt → SecurityObserver extraction)
- Guard LLM — дополнительная зависимость и cost

**Риски:**

- Fail-open: при отказе guard LLM — окно уязвимости (митигация: hardening + canary работают)
- Classifier calibration: false positives/negatives зависят от качества промпта (митигация: итеративная калибровка через Langfuse SUSPICIOUS monitoring)

## Связанные документы

- [security/architecture.md](../../security/architecture.md) — архитектурная документация security
- [security/threat-model.md](../../security/threat-model.md) — threat model
- [research/security/llm-defense-architecture-research.md](../../research/security/llm-defense-architecture-research.md) — research
- [feat-004 design-brief](../../tasks/iterations/post-mvp/feat-004-security/design-brief.md) — детали реализации, 20 decisions
