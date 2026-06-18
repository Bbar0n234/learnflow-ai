# Findings — Resilience toolbox (timeout/retry/fallback)

Дефолты, на которые опирается severity:
- `ChatOpenAI` без `timeout`/`max_retries` → openai-дефолты: **timeout ≈ 600s** (connect 5s), **max_retries=2** + backoff. Формально bounded, но 600s для интерактива = «висит вечно».
- `httpx.AsyncClient()` без аргументов → **дефолт 5s** на все фазы (bounded).
- `redis-py` async `from_url` без `socket_timeout` → **None** → блокировка бесконечно.
- `create_async_engine` → `pool_timeout=30s`, но **`statement_timeout` отсутствует** → запрос может висеть бесконечно.

## Инвентарь внешних вызовов

| Вызов | Локация | Timeout? | Retry? | Fallback? | Sev |
|---|---|---|---|---|---|
| Основной LLM (`bound_model.ainvoke`) | `agent/graph.py:92` | неявн. ~600s | openai x2+backoff | нет | 🟡 |
| LLM-суммаризация | `agent/graph.py:69` | неявн. ~600s | openai | **да** trim-only (`:81-83`) | 🟢 |
| LLM guard-классификатор | `agent/security/classifier.py:100` | неявн. ~600s | bounded loop на невалидный *вывод* (не транзиент) | нет | 🟡 |
| Конструктор LLM (корень) | `infra/llm.py:86-97` | **не задаётся** | — | — | 🟡 |
| MCP fetch tools (resolver) | `services/mcp_tool_resolver.py:150-167` | да, 30s | нет | нет | 🟢 |
| MCP fetch metadata (CRUD) | `services/mcp_server.py:40-64` | да, 30s | нет | 503 | 🟢 |
| MCP test connection | `api/routes/mcp_servers.py:124-130` | да, 30s | нет | success=false | 🟢 |
| MCP builder из конфига | `infra/mcp.py:54-64` | **нет** | нет | нет | 🟡 |
| Langfuse create_score | `api/routes/feedback.py:66-74` | SDK-дефолт | SDK | нет → 503 | 🟡 |
| Langfuse delete (httpx) | `feedback.py:136-141` | неявн. 5s | нет | **идемпотент** (404=ок) | 🟢 |
| Langfuse prompt fetch | `infra/prompt_provider.py:41` | SDK+кэш | SDK | **да** файловый fallback (`:55-58`) | 🟢 |
| DB engine (main) | `infra/db.py:11-12` | pool 30s; **нет statement_timeout** | — | — | 🟡 |
| LangGraph checkpointer/store | `infra/langgraph.py:7-12` | **нет** | — | — | 🟡 |
| Redis (main) | `infra/redis.py:22-25` | **нет** socket_timeout | нет | graceful старт (None) | 🟡 |
| Redis xadd publish | `security_pipeline/transport.py:103` | нет | фон. цикл, событие теряется | drop+метрика | 🟡 |
| Redis TraceStore | `repositories/trace_store.py:23-44` | нет | нет | best-effort в вызывающих; `get_by_thread` в `feedback.py:33` — в request-path | 🟡 |
| SIEM Redis + startup ping | `siem .../main.py:51-52` | **нет**; ping не обёрнут | нет | нет | 🟡 |
| SIEM subscriber XREADGROUP | `siem .../pipeline/subscriber.py:130-136` | да, block=1000ms | **да** supervised exp backoff; идемпот. `on_conflict_do_nothing` | — | 🟢 |
| SIEM DB engine | `siem .../infra/db.py:16-22` | pool 30s; **нет statement_timeout** | — | — | 🟡 |
| SIEM correlation poll | `siem .../main.py:71-78` | poll_interval | **да** supervised backoff | — | 🟢 |

Межсервисное main↔siem — только через Redis Stream `security.events` (прямых HTTP нет).

## Findings (выжимка)
- **[F-RES-01]** 🟡 (для request-path ~🔴) Redis без socket_timeout (`infra/redis.py:22`, `siem main.py:51`) — рантайм-операции блокируются бесконечно; `TraceStore.get_by_thread` в request-path фидбэка; SIEM startup-ping не обёрнут.
- **[F-RES-02]** 🟡 Postgres-движки без `statement_timeout` (`infra/db.py:11-12`, `siem infra/db.py:16-22`).
- **[F-RES-03]** 🟡 LangGraph checkpointer/store без таймаутов (`infra/langgraph.py:7-12`) — дёргается на каждом шаге графа.
- **[F-RES-04]** 🟡 LLM-вызовы на 600s-дефолте openai (`infra/llm.py:86-97`; `graph.py:92,69`, `classifier.py:100`) — слишком долго для стрима.
- **[F-RES-05]** 🟡 Langfuse feedback без контроля таймаута, сбой → 503 (некритичное → лучше degrade).
- **[F-RES-06]** 🟡 MCP builder из статической конфигурации без таймаута (`infra/mcp.py:54-64`) — рассогласование с 30s на других путях.
- **[F-RES-07]** 🟢 Circuit breaker / bulkhead отсутствуют — осознанно, для масштаба не нужно. Частично роль играют bounded queue drop-newest (`transport.py:46-64`) и supervised exp-backoff.

## Рекомендуемые дефолты (предложение)
- **httpx:** всегда явный `httpx.Timeout(...)`, единый клиент-фабрикатор, значения из Settings.
- **LLM:** явный `timeout` << 600s (раздельно чат / суммаризация / guard) + явный `max_retries` в `_build_chat_model`; в Settings/AgentConfig.
- **Redis:** `socket_connect_timeout` + `socket_timeout` на каждом `from_url`, одинаково в обоих сервисах.
- **Postgres:** `statement_timeout` через connect_args/server_settings; pool_timeout явным; pool_pre_ping сохранить.
- **MCP:** единая константа `MCP_TIMEOUT=30` на всех путях, включая `infra/mcp.py`.
- **Retry-политика:** только идемпотентные операции, bounded, exp backoff + jitter; операции с побочками без ключа идемпотентности не ретраить.
- **Деградация:** некритичные сторонние вызовы (Langfuse) — best-effort, не превращать сбой в 5xx.

## Приоритет правок: 6 точек без верхней границы (могут висеть бесконечно)
1. Redis main (`infra/redis.py:22`); 2. Redis SIEM + ping (`siem main.py:51`); 3. DB main statement_timeout (`infra/db.py:11`); 4. DB SIEM (`siem infra/db.py:16`); 5. LangGraph checkpointer/store (`infra/langgraph.py:7-12`); 6. MCP builder (`infra/mcp.py:54-64`). + LLM 600s (`infra/llm.py:97`).
