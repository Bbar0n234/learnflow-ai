# Test Cases: feat-007 — Cross-Cutting Error Handling

Консолидация. Детальные кейсы по трекам — в `test-cases-T1.md`…`test-cases-T5.md`. Кейсы описывают **целевое** поведение (код реализуется в этой итерации). Инфраструктура автотестов — feat-009; здесь преимущественно ручные кейсы + точечные временные автотесты на критичных путях (архивируются в артефакты, не оседают в `backend/tests/`).

## Обзор
| Трек | Кейсов | 👤 | Точечные автотесты (кандидаты) |
|------|--------|----|-------------------------------|
| T1 модель ошибок + барьер | 29 | 6 | — |
| T2 устойчивость + config | 24 | 5 | T2.4/5/6/7/12/22 |
| T3 agent | 14 | 3 | T3.3/4/5/6/7/8/9/10 (целостность thread + обе дороги guard) |
| T4 siem | 17 | 9 | T4.7/10 |
| T5 frontend | 25 | 13 | T5.2–T5.12 (парсер + предикат ретраев) |
| **Итого** | **109** | **36** | |

## Layer 0 — глобальный automated gate
- `make check` (ruff + mypy) — backend (T1/T2/T3/T4).
- `make check-fe` (ESLint + Prettier) — frontend (T5).
- mypy валидирует `AGENT_GUARD_DEGRADED` в `EventType` Literal на call-site (T3).

## Критичные пары-страховки (gate реализации)
- **T2.18 + T2.19** — долгий agent-turn (>120s) НЕ рубится, при этом `idle_in_transaction_session_timeout` НЕ введён. Доказывает per-statement-семантику `statement_timeout`.
- **T3.3** — после исключения в tool thread остаётся валидным, re-entry на тот же `thread_id` не ломается (нет висячего tool_call). Закрывает корневой баг (`empirical-reentry-toolnode.md`).
- **T4.12 + T4.13** — poison-событие дропается (drop+XACK), транзиентный сбой остаётся в PEL (НЕ XACK) и переобрабатывается. Закрывает F-SIEM-02 (потеря security-событий).

## Cross-cutting (Layer 2/3, после всех треков)
- Зеркала `problem.py` (main ↔ siem) консистентны по форме (T1 + T4, полное зеркало по OQ-C): оба несут 3 слоя, одинаковый shape problem+json.
- Контракт problem+json от backend (`type=urn:learnflow:<code>`, extensions) совпадает с тем, что парсит frontend `api-error.ts` (T1/T4 ↔ T5).
- Необработанное исключение → 500 problem+json + CORS-заголовки (оба сервиса).
- Миграции не затрагиваются (схема не меняется) — отдельной проверки БД-миграций не требуется.

## OQ-резолюции, снимающие условность кейсов
Кейсы, помеченные авторами как условные на Open Questions, раскрываются по принятым резолюциям (`decisions.md` § Резолюции):
- validate_url: DNS→400 / SSRF-policy→422 (T1.* по url_validator).
- `MCP_ENCRYPTION_KEY not configured` → 503.
- feedback.py входит в scope T1 (T1.27/T1.28 применимы).
- PDF-таймаут: try/except в T1, Settings-поле в T2 (T1.24).
- 🟢-находки (encryption/url_validator) включены (T1.12).
- handle_tool_errors = callable (T3 кейсы про лог exc_info применимы).
- siem — полное зеркало (T4 кейсы про доменные исключения/иерархию применимы).

## 👤 — ручные/стендовые (36)
Требуют LLM-ключа, браузера или полного стенда (Redis+PG). Прогоняются архитектором/на стенде; в автоматическом gate не участвуют. Перечень — в каждом `test-cases-T*.md` (раздел 👤).
