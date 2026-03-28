# Post-Implementation Summary: feat-003 — SSE Streaming E2E

## Результат

Реальный cancel заменил заглушку в `LangGraphAgentRunner`. Обработка ошибок и неожиданного завершения стрима добавлена на frontend. SSE E2E верифицирован через Chrome с реальным LLM — 6 из 8 тестовых сценариев пройдены (2 негативных отложены).

## Отклонения от плана

### 1. Cancel race condition — pending cancel (ревью-фикс)

**План:** `cancel()` возвращает `False` если `thread_id` нет в `_cancel_events`.

**Факт:** при ревью обнаружена race condition — между `startStream()` на frontend и регистрацией `cancel_event` в `runner.stream()` есть окно, когда cancel не сработает. Реализован двусторонний fix:

- **Backend:** `_pending_cancels: set[uuid.UUID]` — если `cancel()` вызван до `stream()`, thread_id запоминается. При старте `stream()` проверяется pending set, event сразу ставится. `cancel()` теперь всегда возвращает `True`.
- **Frontend:** `cancelChat().then(({ok}) => { if (!ok) abortRef.current?.abort() })` — client-side abort как fallback. AbortError handler вызывает `endStream()` при `isCancellingRef === true`.

### 2. Frontend cancel — `.then()` вместо `.catch()` only

**План:** только `.catch()` с reset `isCancellingRef`.

**Факт:** `.then()` + `.catch()` — `.then()` проверяет `ok` и abort'ит при `false`, `.catch()` тоже abort'ит (network error = cancel не дошёл). Reset `isCancellingRef` в `.catch()` убран — вместо него abort, который вызовет `endStream()` через AbortError handler.

## E2E тесты (Chrome, реальный backend + LLM)

| Тест | Статус | Комментарий |
|------|--------|-------------|
| SSE-1: text_chunk | PASS | Текст появляется инкрементально |
| SSE-2: tool_start / tool_end | PASS | Firecrawl MCP — индикатор появляется и исчезает |
| SSE-3: artifact_created | PASS | ArtifactCard в чате, Artifacts tab обновляется |
| SSE-4: done | PASS | UI в idle, сообщения загружены с сервера |
| SSE-5: error (LLM) | Отложен | Не провоцировался при тестировании |
| SSE-6: cancel | PASS | Стрим прерывается, UI в idle без ошибки |
| SSE-7: network drop | Отложен | Требует kill backend mid-stream |
| SSE-8: повторная отправка | PASS | Новый стрим после done/cancel работает |
| Pending cancel (curl) | PASS | `POST /cancel` до `POST /messages` → стрим сразу cancelled |

## Known Issues

- **Cancel не откатывает HumanMessage в checkpointer** — при cancel LangGraph уже сохранил `HumanMessage` в state, но `AIMessage` не создан. Следующий запрос видит два user-сообщения подряд без assistant-ответа между ними. Сильная модель обрабатывает корректно, слабая может "склеить" контекст. Решение: rollback state после cancel (требует исследования LangGraph API). Бэклог.
- **SSE-5, SSE-7 не верифицированы** — негативные сценарии (ошибка LLM, network drop) отложены. Код для обработки на месте (`terminated` flag, `onError`), но не протестирован E2E.

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `backend/app/agent/runner.py` | + `_cancel_events` dict, `_pending_cancels` set, cancel check в `stream()`, реальный `cancel()` с pending support |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | Cancel: `.then()`/`.catch()` с abort fallback, AbortError → `endStream()` при cancel. Stream: `terminated` flag, "Connection lost" при unexpected end |
| `doc/tasks/tasklist-integration.md` | feat-003 статус → Done |
| `doc/tasks/iterations/integration/feat-003-sse-e2e/plan.md` | Implementation plan |
| `doc/tasks/iterations/integration/feat-003-sse-e2e/summary.md` | Этот документ |
