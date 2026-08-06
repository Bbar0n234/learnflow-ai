# ADR-015: LangGraph Store как unified memory backend

## Статус

Принято

## Контекст

Knowledge Sphere уже живёт в LangGraph Store (`AsyncPostgresStore`, namespace `("project", pid, "sphere")`) — решение из [ADR-003](ADR-003-knowledge-sphere.md). feat-003 Track B добавляет два новых слоя памяти:

- **Custom Instructions** — per-user поведенческие директивы, задаёт пользователь, агент читает (read-only)
- **User Memory** — per-user cross-project заметки, агент пишет автономно

Вопрос: где хранить новые слои? Два кандидата — тот же LangGraph Store (другие namespaces) или PostgreSQL (поля на моделях / отдельные таблицы).

## Решение

Все слои памяти — через LangGraph Store. Разделение через namespaces:

```python
("user", user_id, "instructions")              # Custom Instructions (1 item, key="default")
("user", user_id, "memory")                    # User Memory (N items, key=slug)
("project", project_id, "sphere")              # Knowledge Sphere (без изменений)
("user", user_id, "skill_context", skill_name) # Skill Context (N items per skill, key=doc key)
```

Новые таблицы в PostgreSQL не создаются. Store = единственный storage для агентской и пользовательской памяти. Все слои читаются в `agent_node` через один API (`aget`, `asearch`), инжектируются в system message через единый `prompt_builder`.

## Альтернативы

### PostgreSQL для user-level данных (отклонено)

Custom Instructions как `TEXT` поле на модели `User` или отдельная таблица. User Memory как таблица `user_memories` с FK на `users`.

**Причина отклонения:** два storage backend для семантически однотипных данных (память агента). Дублирование паттернов — для каждого нового слоя нужны model + repository + migration + service, тогда как Store API (`aput`/`aget`/`asearch`) уже готов и используется для KS. Усложнение `agent_node` — два источника данных вместо одного.

### Гибрид: PostgreSQL для instructions, Store для memory (отклонено)

Instructions — "настройка пользователя", ближе к user profile → PostgreSQL. Memory — "агентские заметки", ближе к KS → Store.

**Причина отклонения:** граница искусственная. Оба типа данных читаются агентом из system message одинаковым образом, оба key-value по природе, оба не требуют SQL-запросов или FK constraints. Разные backends усложняют код без выигрыша в функциональности.

## Следствия

- **Единый паттерн расширения:** все будущие типы памяти (per-chat instructions, org-level guidelines, semantic memory с embeddings) идут через Store — новый namespace, тот же API. Skill Context (namespace `("user", user_id, "skill_context", skill_name)`, четырёхуровневый — коллекция документов на скилл, а не одна запись) — первое подтверждение паттерна на практике
- **Нет миграций** для memory-related features — namespace создаётся при первом `aput`
- **Trade-off: нет SQL-queryability.** Нельзя `SELECT ... WHERE created_at > ...` или join с другими таблицами. Приемлемо — память читается по конкретному namespace, сложные запросы не нужны
- **Trade-off: нет FK constraints.** Удаление пользователя не каскадирует на его память в Store. Требует application-level cleanup. Приемлемо на текущем масштабе (один пользователь)
- Store `setup()` автоматически создаёт таблицы (`store_items`, `store_namespaces`) — дополнительная инфраструктура не нужна
