# Post-Implementation Summary: integration/feat-001 — Backend Internal Wiring

## Результат

Подтверждено, что Backend Core и Agent Runtime полностью связаны: Service Layer использует реальные реализации (`LangGraphAgentRunner`, `LangGraphSphereService`), стабы не используются. Все критерии приёмки пройдены через smoke-тесты.

## Отклонения от плана

### 1. Исправление `make type-check` (не в плане)

**Проблема:** `make type-check` (`uv run mypy backend/`) падал с ошибкой `No module named 'pydantic'`. В UV workspace `uv run` без `--package` запускает от имени root-пакета, у которого нет pydantic в зависимостях, но mypy-плагин `pydantic.mypy` требует его в рантайме.

**Решение:** добавлен `--package learnflow-backend` в Makefile для `type-check`, `check` и `test` — штатный механизм UV для workspace.

### 2. Cleanup `.env.local.example` (не в плане)

**Проблема:** файл содержал `LLM_API_KEY` и `LLM_BASE_URL`, которые идентичны значениям из `.env`. По документированной семантике (conventions.md) `.env.local` содержит только переопределения для local dev — разницу в `DATABASE_URL` (host `db` → `localhost`). API-ключи не меняются между режимами.

**Решение:** удалены `LLM_API_KEY` и `LLM_BASE_URL` из `.env.local.example`.

### 3. Sphere PUT с H1-контентом (наблюдение)

**Проблема:** `_parse_markdown_sections()` в `LangGraphSphereService` разбирает контент только по H2 (`##`) заголовкам. Контент без H2 (plain text, H1) молча отбрасывается — PUT возвращает 200, но GET показывает пустой content.

**Контекст:** для агента это нормально — он генерирует sphere с H2-секциями. Но для пользовательского PUT через UI это ловушка: данные теряются без ошибки.

**Решение:** не в scope итерации. Зафиксировано как known issue для будущих итераций. Возможные направления: валидация на уровне API (400 если нет H2), fallback-секция для текста без заголовков, или документирование формата.

## Smoke-тесты

| Тест | Результат |
|------|-----------|
| POST /projects/ → создание проекта | ✅ 200, UUID |
| POST /chats → создание чата | ✅ 200, thread_id |
| POST /messages → SSE stream | ✅ text_chunk от реального LLM + done |
| GET /sphere → чтение | ✅ 200, пустой content (sphere не заполнена) |
| PUT /sphere → запись | ✅ 200, content сохранён |
| GET /sphere после PUT | ✅ content отражает изменения |
| Второе сообщение в тот же чат | ✅ LLM помнит контекст |
| GET /chats/{id} → история | ✅ 4 сообщения (2 user + 2 assistant) |

## Файлы изменены

| Файл | Изменение |
|------|-----------|
| `backend/app/services/agent_runner.py` | Удалён `StubAgentRunner` (мёртвый код) |
| `backend/app/services/__init__.py` | Убран `StubAgentRunner` из импорта и `__all__` |
| `Makefile` | Добавлен `--package learnflow-backend` для type-check, check, test |
| `.env.local.example` | Удалены лишние LLM_API_KEY, LLM_BASE_URL |
| `doc/tasks/tasklist-integration.md` | Статус feat-001 → Done, чекбоксы |

## Known Issues

- **`Message.created_at: null`** — LangGraph checkpointer не хранит timestamps. Уже задокументировано в fix-001 (nullable mismatches).
- **Sphere silent data loss** — PUT с контентом без H2-секций молча отбрасывает данные. См. отклонение #3.
