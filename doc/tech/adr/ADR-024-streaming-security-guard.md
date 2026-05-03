# ADR-024: Streaming Security Guard — Live Stream with Post-Classifier Validation

## Статус

Принято

## Контекст

FINAL_OUTPUT — outbound checkpoint, работающий в streaming-режиме. LLM генерирует токены, которые Immediately отправляются пользователю через SSE (`text_chunk` events). Ответ может быть длинным (1000+ токенов), стриминг длится несколько секунд.

Security guard должен проверять, что в ответе не утекает PROTECTED-контент (ADR-022). Но пользователь ожидает Immediate feedback — каждый токен появляется на экране в реальном времени.

Два конфликтующих требования:
- **Security:** утечка PROTECTED-контента недопустима
- **UX:** буферизация ответа на секунды перед началом отдачи — неприемлемое ухудшение опыта

Sec 1.0 проверял только canary через substring match — быстрый, применимый per-chunk. Sec 2.0 добавляет Paired Tool-Identifier и Fragment детекторы (ADR-023), а также LLM classifier на полный ответ. Вопрос: как совместить streaming с post-classifier validation?

## Рассмотренные варианты

### A: Буферизировать весь ответ, проверять classifier, потом стримить

Полный ответ накапливается в буфере, проходит LLM classifier (1–3 сек), затем отправляется клиенту.

- **За:** гарантия — пользователь никогда не видит утечку
- **Против:** seconds-long задержка перед первым токеном. Для educational платформы с длинными ответами — неприемлемое ухудшение UX. Основная масса ответов (99%+) — легитимные, задержка накладывается на всех

### B: Async parallel guard

Запускать LLM classifier параллельно с основным LLM на partial output. Проверка идёт в фоне.

- **За:** нулевой impact на TTFT
- **Против:** race conditions (classifier вернул INJECTION после того, как LLM уже начал tool calls); partial output у клиента; сложный cleanup (cancel в середине stream); shared events. Архитектурная сложность несоразмерна MVP scope (отвергнуто ещё в ADR-017 для sync vs async)

### C: Live stream + deterministic per-chunk + LLM end-of-stream (выбрано)

Стриминг идёт живым. На каждом chunk — deterministic детекторы на cumulative буфере (<1 ms). После завершения стрима — LLM classifier на полном ответе. При детекции на любом уровне — replace/redact уже отправленного контента.

## Решение

### Mid-stream: deterministic per-chunk

Каждый chunk обновляет cumulative буфер `full_response`. Deterministic детекторы (Canary, Paired, Fragment) прогоняются на **tail** буфера — не на всём накопленном тексте, а на `full_response[-(overlap + chunk_len):]`. Overlap = `max(len(canary_token), fragment.window_size)`. Ранее совпавшие windows уже дали бы hit на предыдущем chunk — short-circuit.

При INJECTION на любом deterministic детекторе:
1. Текущий chunk **не отправляется** клиенту
2. Стрим обрывается
3. Runner вызывает `graph.aupdate_state(config, {"messages": [synthetic AIMessage с security_redacted=True]}, as_node="agent")` — replace-by-id через `add_messages` reducer
4. Runner ставит `thread_views.security_blocked = True`
5. Runner отправляет SSE `security_block` event
6. Frontend заменяет уже отрисованный текст на заглушку

### End-of-stream: LLM classifier

После завершения `graph.astream` — LLM classifier на полном ответе. Во время работы classifier (1–3 сек) frontend показывает последний chunk — дополнительный индикатор ожидания не вводится.

При INJECTION:
1. `aupdate_state` дописывает `security_redacted=True` к финализированному AIMessage
2. `mark_security_blocked` на thread
3. SSE `security_block`
4. Frontend заменяет весь текст на заглушку

### Message-level redaction

Оригинальный content сохраняется в checkpointer (audit-источник). При чтении истории: если `additional_kwargs["security_redacted"] is True` → DTO-mapper подставляет заглушку и выставляет `redacted: true` для UI. Frontend рендерит `"[Сообщение скрыто в целях безопасности]"` — единая константа для mid-stream, end-of-stream и history.

### Block mechanics

При срабатывании guard на runtime checkpoint (не только FINAL_OUTPUT):
- **Thread-level:** `thread_views.security_blocked = True`. FastAPI Depends `require_unblocked_thread` на POST `/messages` → 403
- **Message-level:** `security_redacted` на конкретном сообщении. Оригинал сохранён для audit
- **SSE:** `security_block` event — terminal, frontend обрабатывает специфичным UI (replace + input block)

Подмена сообщений через `add_messages` reducer + synthetic messages с тем же `id`. Отдельная interceptor-нода не вводится — это сохраняет встроенный `tools_condition` LangGraph.

### Observability

Langfuse observation per guard call: `guardrail` type, `guard-{checkpoint}` name. Mid-stream per-chunk calls **не** создают отдельных observations — только при INJECTION (одна observation с `mode="mid_stream"`, полным контекстом детекции). End-of-stream classifier — всегда одна observation.

## Обоснование

- **UX > guarantee of concealment:** 99%+ ответов легитимные. Задерживать всех ради редких утечек — несоразмерно. Пользователь может кратко увидеть утечку до post-classifier замены — осознанный trade-off, приоритет UX.
- **Deterministic per-chunk достаточно быстр:** <1 ms на tail буфера. Latency budget p90 <2s на весь guard pipeline (подтверждено на 85 атакующих кейсах Sec 1.0).
- **LLM classifier закрывает semantic gap:** deterministic не ловят парафраз. End-of-stream на полном ответе — максимум контекста для классификатора, лучший FN rate.
- **Replace-by-id через reducer:** встроенный механизм LangGraph `add_messages`. Не требует изменения топологии графа, нод, Command API. Synthetic message с тем же `id` перезаписывает оригинал.
- **Почему не interceptor-нода:** отдельная нода в топологии потребовала бы conditional edge после неё и переписывания routing. Inline в `agent_node` + runner достигает той же семантики кратно меньшим кодом.

## Следствия

- **Acknowledged tradeoff:** brief exposure PROTECTED-контента возможен между моментом генерации и post-classifier детекцией. Митигация: deterministic детекторы на каждом chunk ловят exact/near-exact утечки в реальном времени.
- **Frontend:** два path'а для `security_block` — после `text_chunk` (mid-stream, уже отрисованный текст) и при GET истории (`redacted: true` на сообщении). Единая заглушка.
- **Tail-only scan:** упрощённый overlap `max(len(canary_token), 64)`. Риск: tool с именем >50 символов через границу chunks может быть пропущен mid-stream. End-of-stream classifier и full FINAL_OUTPUT scan всё равно сработают.
- **Thread-level block необратим** в рамках текущей итерации. Разблокировка — через отдельный admin-инструмент (feat-007 SIEM Extensions).
- **Add-time checkpoints** (MCP_METADATA, CUSTOM_INSTRUCTIONS_WRITE, KS_WRITE_REST) не участвуют в streaming — они работают в request scope, ответ синхронный (422).

## Связанные документы

- [ADR-022](./ADR-022-protected-disclosable-boundary.md) — PROTECTED/DISCLOSABLE boundary
- [ADR-023](./ADR-023-two-level-detection.md) — deterministic + LLM detection layers
- [ADR-017](./ADR-017-prompt-injection-defense.md) — Sec 1.0: sync guard, fail-open
- [security/architecture.md](../../security/architecture.md) — block mechanics, coverage map
- [feat-006 design-brief](../../tasks/iterations/post-mvp/feat-006-security-2.0/design-brief.md) — §5 (coverage map, FINAL_OUTPUT streaming), §6.5 (runtime integration), §6.8 (thread-level block), §6.9 (message-level redaction), §8.1 (latency budget)
- [feat-006 summary](../../tasks/iterations/post-mvp/feat-006-security-2.0/summary.md) — SSE cross-scope side effect, replace-by-id implementation
