# Code Review — T4 (siem-service), feat-007 cross-cutting

Ревьюер: code-reviewer (домен siem-service). База diff: `git diff develop...HEAD -- services/siem-service`.
Норма: `decisions.md` (D-ERR-7, OQ-C/D/E), `plan-T4.md`, `conventions.md` § Обработка ошибок / § REST API / § Logging.
Образец зеркала: `backend/app/api/problem.py`, `backend/app/services/exceptions.py`.

## Summary

Трек T4 реализован близко к плану и зеркалит main app по форме: своя иерархия `AppError`
(`siem_service/exceptions.py`) + барьер 3 слоя в `problem.py` + роуты на доменные исключения
(полное зеркало, OQ-C). Критичная для безопасности логика subscriber'а (D-ERR-7 / OQ-E)
**корректна**: транзиентный инфра-сбой не XACK-ается (остаётся в PEL), bounded delivery-count
через `XPENDING.times_delivered` реально растёт на каждом переразборе и терминирует после N —
зацикливания нет. Это проверено эмпирически на Redis 7.4 (см. ниже). Literal на
`rule_type`/`severity`, строгий `get_strategy` (raise в per-rule try/except движка),
`IntegrityError → ConflictError (409)`, event_id из `event_dict`, `_read_pending` с причиной,
наблюдаемость meta-emitter — всё на месте. `make check` зелёный (по summary), env-переменные
(`SIEM_MAX_DELIVERY_ATTEMPTS` и пр.) синхронизированы в `.env.example` / `.env.local.example` /
`docker-compose.yml`.

Один **blocker**: generic-500 + CORS на деле **не работает** — middleware зарегистрирован после
CORS и оказывается *снаружи* CORS, 500-ответ уходит без `Access-Control-Allow-Origin`. Это
точное зеркало того же дефекта в main app (T1), но цель OQ-2 / F-API-01 не достигнута ни там,
ни здесь. Остальное — nit / nice-to-have.

### Эмпирические проверки (вне диффа, для протокола)

1. **bounded-счётчик / зацикливание (D-ERR-7, критично).** Поднял `redis:7-alpine` (7.4.8),
   проверил инкремент `times_delivered`: первое `XREADGROUP '>'` → 1; повторный
   `XREADGROUP '0'` (путь `_read_pending`) → 2 → 3. То есть переразбор PEL **инкрементирует**
   delivery-count, `delivery_count > max_delivery_attempts` достижим, terminal-drop срабатывает.
   Транзиент остаётся в PEL и переобрабатывается, счётчик не зацикливает. **Корректно.**
   (Опасение, что `XREADGROUP '0'` не инкрементит счётчик — для 7.x опровергнуто.)
2. **CORS-on-500.** Минимальный FastAPI+TestClient репро двух порядков middleware:
   порядок «CORS, затем generic» (как в siem и main app) → `Access-Control-Allow-Origin = None`
   на 500; порядок «generic, затем CORS» → заголовок присутствует. Подтверждает B1.
3. **Путь re-raise → supervisor.** `supervised()` рестартует с backoff бесконечно; на рестарте
   PEL перечитывается (delivery-count растёт) → даже «прочее необработанное» (баг кода) в итоге
   терминируется тем же bounded-счётчиком. Перманентного клина нет.

## Findings

| ID | Severity | Файл | Находка |
|----|----------|------|---------|
| B1 | blocker | `siem_service/main.py:118-137` (+ docstring `api/problem.py:9-11`) | generic-500 middleware добавлен **после** `CORSMiddleware` → в стеке Starlette оказывается *снаружи* CORS. 500-ответ, сформированный в нём, не проходит обратно через CORS и не получает `Access-Control-Allow-Origin`. Комментарий «sits below CORSMiddleware» фактически неверен (он выше). Цель OQ-2 / F-API-01 (CORS на 500) не достигнута. Эмпирически подтверждено. Фикс: регистрировать generic-middleware **до** `add_middleware(CORSMiddleware, ...)`. Зеркальный дефект присутствует и в main app (`backend/app/main.py:514-556`) — чинить на уровне паттерна (оба `main.py` + поправить docstring в обоих `problem.py`). |
| N1 | nit | `siem_service/pipeline/subscriber.py:172-174` | `_get_delivery_count`: `except Exception: pass` без лога. Решение (fallback=1) задокументировано, но молчаливое глотание противоречит § Барьерный стек («except: ... без логирования» — антипаттерн). Если `XPENDING` устойчиво падает (Redis-деградация), bounded-защита тихо отключается. Добавить `logger.debug/warning(..., exc_info=True)` перед fallback. |
| N2 | nice-to-have | `siem_service/pipeline/subscriber.py:193` | `_get_delivery_count` делает отдельный `XPENDING` round-trip для **каждого** сообщения, включая здоровую первую доставку (где count всегда 1). На happy-path удваивает Redis-обращения на событие. Можно проверять delivery-count только для PEL-пути (`_read_pending`), для новых (`>`) сообщений он заведомо 1. Механизм по OQ-E корректен, это лишь оптимизация. |
| N3 | nice-to-have | `siem_service/pipeline/meta_emitter.py:61-66` | Сбой эмиссии meta-события логируется на `ERROR`, при этом действие админа успешно (graceful degradation). § Восстановление предписывает `warning + exc_info` для некритичного fallback. Уровень `ERROR` защитим (дроп security-аудита), но расходится с конвенцией. Решить уровень осознанно (warning по конвенции vs error по весу security-аудита). |

## Blocker без прецедента

**B1 — не имеет задокументированного прецедента/принятого отклонения.** Это реальный
неисправленный дефект, а не согласованная девиация: ни `decisions.md` (OQ-2/D-ERR-2), ни
`plan-T4.md`, ни `summary.md` не фиксируют «CORS на 500 не работает» как принятый компромисс —
напротив, summary T4 утверждает «CORS-on-500 работает корректно», что неверно. Дефект системный
(идентичен в уже смердженном T1 main app), поэтому фикс уместен на уровне общего паттерна, а не
точечно в siem.
