# Implementation Plan: feat-007 — Cross-Cutting Error Handling

## Контекст
Итерация feat-007 (codebase-maturity). Источники: `decisions.md` (D-ERR-1…11, роль design-brief), `audit-findings.md` + `audit-raw-0X.md` (findings), `conventions.md` § «Обработка ошибок» (спека норм), `empirical-reentry-toolnode.md`.

План декомпозирован на 5 треков по доменам. Детали фаз — в фрагментах `plan-T1.md`…`plan-T5.md`. Этот файл — консолидация: карта пересечений, порядок исполнения, сводные Open Questions, cross-cutting verification.

## Треки (см. фрагменты)
| Трек | Домен | Фаз | Файлы (кратко) |
|------|-------|-----|----------------|
| T1 | Модель ошибок + барьер (main app) | 8 | `services/exceptions.py`, `api/problem.py`, `main.py`, `services/{sphere,user_memory,mcp_server,auth,encryption,url_validator}.py`, `api/{export,routes/artifacts,routes/messages,routes/feedback}.py` |
| T2 | Устойчивость + config (оба сервиса) | 6 | `config.py`×2, `infra/{redis,db,langgraph,llm,mcp}.py`, `services/mcp_tool_resolver.py`, `services/mcp_server.py`, `routes/mcp_servers.py`, `main.py`×2, siem `infra/db.py`, `.env.example`, `docker-compose.yml` |
| T3 | Agent error handling | 7 | `packages/siem-contracts/{vocabulary,__init__}.py`, `agent/security/{types,classifier,guard}.py`, `agent/{graph,runner}.py`, `doc/security-events.md` |
| T4 | SIEM error handling | 6 | siem `api/{problem,routes}.py`, `pipeline/{subscriber,meta_emitter}.py`, `correlation/strategies.py`, `domain/schemas.py`, `services.py`, `repositories.py`, `config.py`, env |
| T5 | Frontend (обвязка) | 9 | `frontend/src/shared/{api/client,api/security,lib/api-error}.ts`, `app/providers/QueryProvider.tsx`, ~13 компонентов |

## Карта пересечений файлов

Мутуально **дизъюнктны**: T1 ⊥ T3 ⊥ T4 ⊥ T5 (разные директории: main-app api/services / agent / siem / frontend).

**T2 — хаб**, пересекается с остальными:
| Файл | Треки | Severity |
|------|-------|----------|
| `backend/app/main.py` | T1, T2 | высокая |
| `backend/app/services/mcp_server.py` | T1, T2 | высокая |
| `backend/app/api/routes/mcp_servers.py` | T2 (T1 ripple) | средняя |
| siem `main.py` | T2, T4 | высокая |
| siem `config.py` | T2, T4 | средняя |
| `.env.example`, `docker-compose.yml` | T2, T4, (T5 .env) | низкая (append) |

Снятые ложные пересечения: `vocabulary.py` правит **только T3** (T4 подтвердил, что не трогает `EventType`).

Content-зависимости (не файловые): T4 `problem.py` — зеркало формы T1 `problem.py` (синхронизировать); T5 парсер — читает контракт problem+json из T1/T4 (уже задан в конвенциях).

## Порядок исполнения (предложение)
Дизъюнктные T1, T3, T4, T5 не конфликтуют по файлам ни между собой, ни (кроме T2) с хабом. T2 нельзя исполнять одновременно с T1 и T4. T1⊥T4.

- **T3 и T5** — изолированы, идут параллельно в любой момент.
- **Backend-цепочка:** T2 ↔ T1 и T2 ↔ T4 — не одновременно. T1 ∥ T4 (дизъюнктны). Варианты: `T2 → (T1 ∥ T4)` либо `(T1 ∥ T4) → T2`.
- Механизм конкуренции (серийно в одном worktree vs эфемерная изоляция на агента) — решение архитектора (см. эскалацию: гонка git-index + одновременный `make check` в общем worktree).

## Сводные Open Questions
Полный разбор с рекомендациями — в эскалации оркестратора. Требуют решения архитектора:
- **OQ-A (T3):** `handle_tool_errors` — callable (логирует exc_info + возвращает безопасный content) vs `=True` (молча). D-ERR-5 буквой пишет `=True`, но это противоречит «лог + метрика».
- **OQ-B (T3):** «метрика» при отсутствии metrics-инфраструктуры (нет Prometheus/StatsD) — канал через `security_event`(SIEM) + `logger.error`, без выделенного счётчика.
- **OQ-C (T4):** у siem нет иерархии `AppError`/`exceptions.py` — зеркало барьера ограничить слоями 2/3 (инфра+generic), роуты оставить на `HTTPException`? Или своё мини-дерево / общий пакет.
- **OQ-D (T2):** siem Redis `socket_timeout` vs блокирующий `XREADGROUP(block=1000ms)` — инвариант `socket_timeout > block` или отдельный клиент.
- **OQ-E (T4):** механика bounded-счётчика попыток D-ERR-7 (сколько → что делаем: drop+лог, без dead-letter).
- **OQ-F (T5):** где документировать новые `VITE_*` (у фронта нет `.env.example`, существующие не задокументированы).

Решаемые оркестратором по базовому принципу (FYI): статус `validate_url` (DNS vs SSRF), статус `MCP_ENCRYPTION_KEY not configured`, механизм CORS-on-500, `AuthError` остаётся локальным (эталон F-API-08), `feedback.py` в scope T1, объём 🟢-находок, libpq-params для LangGraph, SSE first-byte timeout (отдельная ручка), F-FE-08/F-FE-10 включаем как мелкие правки.

## Резолюции и финальный порядок (после планирования)
OQ закрыты (детали — `decisions.md` § Резолюции):
- OQ-A → callable; OQ-B → security_event как метрика, без счётчика; OQ-D → socket_timeout>block; OQ-E → PEL delivery-count→drop+log; OQ-F → `VITE_*` в корневой `.env.example`.
- **OQ-C → полное зеркало:** T4 расширен — siem получает свою иерархию `AppError` (`siem_service/.../exceptions.py`) + барьер 3 слоя + рефактор роутов на доменные исключения (как T1). T4 теперь зависит от паттерна T1.

**Режим: серийно в одном worktree** (эфемерные worktree запрещены). Порядок: **T1 → T4 → T2 → T3 → T5**. Каждый трек: implement → `make check`/`make check-fe` → тест-кейсы трека → локальный коммит. Implementer предупреждается: каталог общий, при неожиданном состоянии — пауза/адаптация.

## Cross-cutting verification
- `make check` (backend) и `make check-fe` (frontend) проходят.
- Зеркала `problem.py` (main ↔ siem) консистентны по форме.
- Контракт problem+json от backend совпадает с тем, что парсит frontend.
- Жёсткое требование T2: НЕ вводить `idle_in_transaction_session_timeout` (statement_timeout — per-statement, ранний commit в `chat.py` не страдает).
- Тест-кейсы — отдельной фазой (после разрешения OQ), преимущественно ручные (инфраструктура — feat-009).
