# Code Review (режим A): feat-003 — T1

Ревьюер: Opus, diff `develop...HEAD` (7 code-коммитов итерации). Дата: 2026-07-24.

## Summary

- blocker: 0 / nit: 1 / nice-to-have: 3

## Замечания

| Severity | Файл:строка | Замечание | Предложение |
|---|---|---|---|
| nice-to-have | `backend/app/services/model_config_resolver.py:81` | `_resolve_extra_body` возвращает сам объект `self._llm_config.extra_body` (общий на все запросы) при наследовании; мутаций на текущих путях нет, но `subagents/runner.py:146` уже защищается копией | Вернуть защитную копию `dict(...)` для консистентности |
| nice-to-have | `backend/tests/agent/test_pricing_external.py:54` | `Settings()` вне try/except: на голом окружении без `JWT_SECRET` → ValidationError → error вместо skip | Занести в try/except (ValidationError → skip) |
| nice-to-have | `backend/tests/agent/test_pricing_external.py:9,61` | Docstring «any non-2xx skips» vs код `== 200` | Синхронизировать формулировку |
| nit | `backend/app/services/model_config_resolver.py:77` | Голый `dict` в сигнатуре vs `dict[str, Any]` у поля-адресата | Привести к `dict[str, Any] \| None` |

## Проверено явно чистым

Regex/lookahead pricing.yaml (уникальность матчей держится, forcing function OQ#1 сохранена); skip-vs-fail семантика external-тестов (RequestError/non-200/non-JSON → skip, расхождение данных → fail; репрайс в ноль ловится); наследование extra_body (приоритеты верны, Langfuse-ветка и default() не тронуты, 3 unit-кейса покрывают ветки); обратная совместимость ReasoningOptions; секретов в diff нет.

## Blocker без прецедента

Нет.

## Резолюция оркестратора

Все 4 замечания взяты в фикс-цикл (implementer). Повторное ревью не требуется (severity низкие, скоуп точечный).
