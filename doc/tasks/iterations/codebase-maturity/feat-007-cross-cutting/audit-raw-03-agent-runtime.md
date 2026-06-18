# Findings — Agent runtime + tools

Scope: `backend/app/agent/` — runner, ноды графа (`graph.py`), tools, security/guard, классификатор, observer, tracer, error_mapper, SSE-маппер.

Главный вывод: контур зрелый — барьер в runner + fail-safe для вспомогательных подсистем. Болевые точки: (1) guard имеет ДВЕ дороги деградации в CLEAN, наблюдаема одна; (2) tools при `store is None` → `RuntimeError` рвёт ход (форк); (3) главный барьер логирует без stack trace.

---

### [F-AGT-01] Главный барьер стрима логирует без `exc_info` и уровнем warning 🟡
- Локация: `backend/app/agent/runner.py:226-234`
- Правило: №3, №7
- Текущее: `except Exception as e: logger.warning("agent stream error", error=str(e)); yield StreamEvent(type="error", ...)`. Трансляция клиенту корректна (`normalize_error_message`), но оператор получает только `str(e)` без exc_info/типа. Все неожиданные ошибки контура долетают именно сюда.
- Направление: на барьере с широким Exception — лог `exc_info=True`, уровень `error`. Кандидат в конвенцию.

### [F-AGT-03] event_type/verdict в логе деградации guard зашиты константой и противоречивы 🟡
- Локация: `backend/app/agent/security/guard.py:152-159`
- Правило: №7
- Текущее: `event_type=AGENT_GUARD_INPUT_CLASSIFIER_INJECTION` зашит для всех направлений (хотя check() обслуживает и OUTBOUND — FINAL_OUTPUT/TOOL_RESULT, где hit-пути выбирают по direction). На FINAL_OUTPUT-сбое в SIEM прилетит INPUT-событие. Конфликт: `event_type=...INJECTION` при `metadata.verdict="clean"`.
- Направление: выбирать event_type по direction; либо отдельный `AGENT_GUARD_DEGRADED`.

### [F-AGT-04] Вторая дорога деградации guard в CLEAN (исчерпание ретраев) НЕ помечена как security-event 🟡
- Локация: `backend/app/agent/security/classifier.py:99-134`
- Правило: №5 (D1), №7
- Текущее: если LLM `max_retries` раз вернул невалидный вердикт → `logger.warning("classifier retries exhausted, degrading to CLEAN", ...)` + `return ClassifierResult(verdict=CLEAN, ...)`. guard.check() получает это как обычный CLEAN — БЕЗ `security_event`, без `event_type`, без `severity`, в GuardResult уйдёт `LLM_CLASSIFIER` (не GRACEFUL_DEGRADATION). SIEM/метрики эту деградацию не видят. Из двух дорог fail-open наблюдаема одна. **Нарушение D1.**
- Направление: унифицировать обе дороги под наблюдаемый GRACEFUL_DEGRADATION-сигнал.

### [F-AGT-05] Tools при `store is None` → `RuntimeError` → ToolNode пробрасывает → SSE error → ход рвётся 🟡 (форк)
- Локация: `tools/user_memory.py:8-9,14-18`; `tools/knowledge_sphere.py:13-22`; путь — `runner.py:158-163,226-234`
- Правило: №2, №3, №5
- Текущее: дефолтный ToolNode ловит только `ToolInvocationError`; `RuntimeError` всплывает → широкий except в runner → `normalize_error_message` (generic) → один error-event, ход завершается (стрим не крашится, finally/trace_id отрабатывают).
- Замечание: доменные ветки тех же тулов graceful (возврат строки `"Error: section ... not found"`, knowledge_sphere.py:34,56,81,92,113). `store is None` — инфраструктурное отсутствие, не доменный кейс. Открытый форк (ниже).

### [F-AGT-11] Удалённые LLM-вызовы без явного timeout 🟡 (смежно с resilience-агентом)
- Локация: `security/classifier.py:100`; `graph.py:92`; `graph.py:69` (summarization)
- Правило: №6
- Текущее: ни основной LLM, ни guard-классификатор, ни суммаризация не имеют видимого в слое timeout (только `max_retries=3`, types.py:121).

### [F-AGT-12] Security side-effects (mark_blocked/redact/persist) глотают исключение в warning 🟢
- Локация: `runtime_security.py:185-217,232-271,290-311`
- Правило: №3, №5
- Текущее: три side-effect-метода: `try/except Exception → logger.warning(exc_info=True)` и продолжают. Следствие: при сбое `mark_security_blocked` тред НЕ помечается заблокированным, хотя клиент получил `security_block`-event — расхождение состояния. Наблюдаемо и осознанно (deadlock на shared-session задокументирован :279-289).
- Направление: решить — достаточно ли warning или нужен security-event/метрика на «не удалось зафиксировать блокировку».

---

## Хорошие примеры

- **[F-AGT-02] ✅ Guard fail-open в CLEAN при LLM-исключении наблюдаемо** (`security/guard.py:143-171`) — по D1: WARNING + `security_event=True` + `severity=critical` + `exc_info` + `DetectionLayer.GRACEFUL_DEGRADATION`. Эталон наблюдаемой деградации (но см. F-AGT-03/04).
- **[F-AGT-06] ✅ normalize_error_message** (`error_mapper.py:16-30`, конфиг `config.py:62-67`) — маппинг типа/имени исключения в безопасные тексты (`generic/timeout/auth/upstream/cancelled`) из yaml; ни путей, ни имён тулов, ни стека клиенту.
- **[F-AGT-07] ✅ Tracing/observer fail-safe** (`tracing.py`, `security/observer.py`) — Langfuse-вызовы в try/except + `_NoOpSpan`; телеметрия отвалилась — ход продолжается. Заметка: `contextlib.suppress(Exception)` без лога допустим только для best-effort-телеметрии.
- **[F-AGT-08] ✅ MCP-резолвинг degrade на глобальные tools** (`runner.py:288-300`) — `except Exception → warning(exc_info) → []`.
- **[F-AGT-09] ✅ Суммаризация → fallback на trim-only** (`graph.py:81-83`).
- **[F-AGT-10] ✅ agent_node: fail-fast на core-store, degrade на персонализации** (`graph.py:225-226` fail-fast / `:234-251` degrade) — живая иллюстрация «core → fail-fast; вспомогательное → degrade». Заметка: `runtime.store.asearch` KS-index (`:228`) не обёрнут — core-отказ, согласовано.

---

## Открытые форки

**(а) `store is None` в tools: fail-fast vs graceful.** Локации: `tools/user_memory.py:8-9,14-18`; `tools/knowledge_sphere.py:13-16,19-22`; `tools/artifacts.py:34-37` (`context is None`) + DB-write в `session.begin()` `:41-49`. Рекомендация агента: оставить fail-fast (отсутствие стора — поломка деплоя, не рантайм-ветка), но настроить маппинг так, чтобы класс ошибок шёл наблюдаемым операторским сигналом, а не сливался в `generic`.

**(б) Наблюдаемость guard fail-open: две дороги, помечена одна.** Дорога 1 (LLM-исключение, `guard.py:143-171`) наблюдаема. Дорога 2 (исчерпание ретраев, `classifier.py:125-134`) тихая. + дефект разметки event_type (F-AGT-03). Решение: (1) унифицировать обе дороги под GRACEFUL_DEGRADATION + security-event + метрика; (2) канонический event_type для деградации; (3) direction по checkpoint.

---

## Итог
12 findings: 🟡 6 / 🟢 1 / ✅ 5.
Топ-3: F-AGT-04+форк(б) (вторая дорога fail-open тихая — нарушение D1), форк(а)/F-AGT-05 (`store is None` RuntimeError рвёт ход), F-AGT-01 (барьер без exc_info).
