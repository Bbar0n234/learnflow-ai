# Референс: Паттерны защиты от Prompt Injection

> Обобщённые паттерны для реализации runtime-защиты LLM-агента от prompt injection.
> На основе industry best practices и OWASP LLM Top 10.

---

## 1. Архитектура защиты

### 1.1. Принцип: проверяй все входы, а не только пользовательский

Prompt injection может прийти не только через пользовательский ввод:

| Источник | Пример |
|----------|--------|
| Пользовательский ввод | Прямая injection: "Ignore previous instructions..." |
| Persistent storage (RAG, memory) | Ранее сохранённые данные со скрытыми инструкциями |
| Результаты tool calls | Вредоносный payload из внешних API/MCP |

**Следствие:** guard должен проверять данные на каждой trust boundary, а не только на входе.

### 1.2. Layered Guards

Два типа проверок, выполняемых последовательно:

1. **Детерминистические** (быстрые, бесплатные) — отсекают тривиальные атаки до LLM call
2. **LLM-классификатор** (дороже, но семантический) — ловит смысловые инъекции

При обнаружении угрозы — блокировка запроса + пометка в observability.

**Санитизация (вырезание инъекций) НЕ рекомендуется** — продолжение с потенциально скомпрометированным контекстом рискованно.

### 1.3. Graduated Response

Вместо бинарного block/allow — спектр реакций:

```
CLEAN       → обычная обработка
SUSPICIOUS  → обработка + усиленное логирование + (опционально) ограничения
INJECTION   → блокировка + логирование + сообщение пользователю
```

---

## 2. Ключевые компоненты

### 2.1. Детекция невидимых Unicode-символов

Проверка текста на символы Unicode-категорий Cf (Format), Co (Private Use), Cn (Unassigned):

- **Cf** — zero-width space (U+200B), zero-width joiner (U+200D/U+200C), BOM (U+FEFF), RTL override (U+202E), soft hyphen (U+00AD)
- **Co** — private use area (U+E000+)
- **Cn** — неназначенные кодпоинты

Кириллица, эмодзи, CJK — легитимные символы, НЕ попадают в эти категории.

Оптимизация: быстрый путь для ASCII-текста (`ord(char) > 127` как pre-check).

### 2.2. LLM-классификатор

LLM получает контекст (историю сообщений с ролями) и классифицирует: содержит ли он попытку инъекции.

**Ключевые design decisions:**

| Решение | Обоснование |
|---------|-------------|
| Парсинг ответа через `startswith` | Модель может добавить reasoning после YES/NO — игнорируем лишнее |
| Retry при невалидном ответе | Reasoning-модели иногда отвечают не по формату |
| Graceful degradation при ошибке LLM | Availability > security: если guard недоступен — пропускаем, не блокируем |
| `temperature: 0` | Детерминированность классификации |
| Bias к false negatives | Для образовательных платформ: блокировка легитимного запроса хуже пропуска атаки, которую поймает output-слой |

**Форматирование входа для классификатора:**

История сообщений оборачивается в XML с ролевыми префиксами. Это повышает точность — классификатор видит структуру диалога:

```
<conversation_history>
[SYSTEM] ...
[USER] ...
[ASSISTANT] ...
[TOOL] ...
</conversation_history>
```

`[SYSTEM]` в промпте классификатора помечается как "legitimate behavioral configuration" — снижает false positives.

---

## 3. Интеграция с Langfuse

### 3.1. Пометка трейса при блокировке

При обнаружении угрозы — обновляем trace и span metadata для фильтрации в dashboard:

```python
# Trace-level metadata (для фильтрации в списке traces)
span.update_trace(
    metadata={
        "security_blocked": True,
        "block_reason": reason,  # "invisible_chars" | "prompt_injection"
    },
)

# Span-level metadata (для детального анализа)
span.update(
    output=blocked_message,
    metadata={
        "status": "security_blocked",
        "block_reason": reason,
        "block_details": details,
    },
)
```

### 3.2. Возможности dashboard

- **Фильтрация:** `metadata.security_blocked = true` → все заблокированные запросы
- **Группировка:** по `block_reason` → соотношение invisible_chars vs prompt_injection
- **False positive анализ:** просмотр текстов заблокированных запросов
- **Метрики:** % заблокированных, тренд по времени, группировка по user
- **Паттерны атак:** trace содержит user_id и session_id

### 3.3. Структура метаданных

```
Trace metadata:
├── security_blocked: true/false
├── block_reason: "invisible_chars" | "prompt_injection" | "canary_leak"
└── (стандартные: user_id, session_id)

Span metadata:
├── status: "security_blocked" | "success" | "error"
├── block_reason: тип обнаруженной угрозы
└── block_details: человекочитаемое описание
```

---

## 4. Known Issues & Limitations

| Проблема | Описание | Митигация |
|----------|----------|-----------|
| False positives | Блокировка при обсуждении темы безопасности | Промпт с bias к FN; full history для контекста |
| Latency | LLM-классификатор добавляет задержку к каждому запросу | Детерминистический guard отсекает часть атак до LLM |
| LLM availability | Классификатор зависит от доступности LLM | Graceful degradation → пропускаем |
| Adaptive attacks | Продвинутые атаки обходят LLM-классификатор | Итеративное улучшение промпта, defense-in-depth |
| Cost | Каждый запрос = дополнительный LLM call | Дешёвые быстрые модели |
