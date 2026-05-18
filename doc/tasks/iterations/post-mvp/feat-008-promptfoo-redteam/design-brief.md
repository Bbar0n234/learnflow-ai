# Design Brief: feat-008 — Promptfoo Red Team Scan

> **Статус:** Draft for implementation. Решение согласовано на уровне архитектуры: Promptfoo + локальный Python provider, без `/scan` endpoint в production API. Документ фиксирует scope, контракты и артефакты так, чтобы агент мог реализовать tooling с нуля.

## 1. Context & Trigger

### 1.1 Trigger

Есть внешнее требование: запустить LLM-specific vulnerability scanner для LearnFlowAI и получить демонстрируемые результаты по prompt injection / jailbreak / leakage сценариям. В качестве baseline рассматривался Garak, потому что он прямо упоминался как пример такого scanner'а.

После сравнения scanner'ов выбран практичный путь через Promptfoo:

- Garak хорошо подходит как узнаваемый LLM vulnerability scanner, но его REST target ожидает простой контур `prompt -> response`. LearnFlowAI API stateful: auth, project/chat lifecycle, SSE stream, thread blocking.
- Promptfoo лучше ложится на app-level testing: поддерживает custom Python provider, redteam plugins/strategies, OWASP mappings и отчеты.
- Scanner должен проверять не базовую LLM-модель, а полный backend contour LearnFlowAI: auth, Agent Runtime, `SecurityGuard`, SSE `security_block`, thread blocking, Langfuse/SIEM observability.

### 1.2 Architectural insight

Scanner-specific integration не должна попадать в production API. Добавление `/scan` endpoint технически возможно, но создаёт лишнюю поверхность, которую нужно защищать, документировать и не забыть выключить.

Правильная граница:

```text
Promptfoo
  -> local Python provider
    -> existing LearnFlowAI REST/SSE API
      -> LangGraph Agent Runtime
        -> SecurityGuard checkpoints
```

Promptfoo генерирует и оценивает adversarial cases. Python provider адаптирует эти cases к существующему API: логинится, создаёт project/chat, отправляет сообщение, читает SSE и нормализует результат. Backend не знает, что его сканируют.

### 1.3 References

- [Promptfoo Python Provider](https://www.promptfoo.dev/docs/providers/python/) — `file://provider.py`, `call_api(prompt, options, context) -> {"output": ...}`.
- [Promptfoo Red Team Configuration](https://www.promptfoo.dev/docs/red-team/configuration/) — `redteam.purpose`, `plugins`, `strategies`, `frameworks`, `numTests`.
- [Promptfoo Output Formats](https://www.promptfoo.dev/docs/configuration/outputs/) — HTML/JSON/CSV/JSONL/YAML/JUnit outputs.
- [OWASP Top 10 for LLM Applications 2025](https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/) — reporting frame for LLM risks.
- [doc/security/architecture.md](../../../../security/architecture.md) — LearnFlowAI security checkpoints and block mechanics.
- [doc/security/threat-model.md](../../../../security/threat-model.md) — Direct / indirect / persistent prompt injection vectors.
- [feat-006 Security 2.0](../feat-006-security-2.0/design-brief.md) — Universal I/O Guard + PROTECTED / DISCLOSABLE boundary.

## 2. Goals

- Добавить воспроизводимый red-team scan для LearnFlowAI без изменения production backend API.
- Использовать Promptfoo как scanner engine и локальный Python provider как adapter к существующему REST/SSE API.
- Проверять реальный backend contour, а не модель напрямую и не mock endpoint.
- Получать human-readable и machine-readable артефакты: Promptfoo report, JSON results, provider event log, ручной summary.
- Хранить scanner tooling в репозитории изолированно от основного приложения.
- Коммитить отчеты прогонов как учебные/аудитные артефакты, если они получены на eval-user и прошли ручной review на секреты.
- Сохранить возможность расширить scan на add-time endpoints (`custom_instructions_write`, `ks_write_rest`, `mcp_metadata`), если это реализуется без тяжёлого рефакторинга.

## 3. Non-Goals

- Не добавлять `/scan` или другой scanner-only endpoint в main app.
- Не менять production behavior `SecurityGuard` / Agent Runtime ради scanner'а.
- Не строить новую security evaluation platform вместо Promptfoo.
- Не реактивировать archived `tools/eval-sec` как часть этой итерации. Он остаётся reference implementation для HTTP/SSE lifecycle.
- Не делать Garak-интеграцию в первой итерации. Garak можно добавить позже поверх того же adapter-подхода или через custom generator.
- Не покрывать file upload prompt injection: upload surface пока планируемый, не текущий runtime.

## 4. Scope

### 4.1 MVP Scope — Chat Runtime Scan

MVP проверяет основной пользовательский контур:

```text
Promptfoo test case
  -> provider sends message
    -> POST /api/projects/{project_id}/chats/{chat_id}/messages
      -> SSE events
        -> normal response OR security_block
```

Покрываемые security surfaces:

| Surface | Как проверяется |
|---|---|
| `user_input` | adversarial prompt отправляется как обычное сообщение пользователя |
| `final_output` | provider читает весь SSE stream и фиксирует `security_block` после/во время генерации |
| `tool_call_arg` | косвенно через атаки, которые пытаются заставить агента вынести PROTECTED content в tool arguments |
| `tool_result` | косвенно для scenarios, где агент вызывает внешние tools; полноценная indirect setup остаётся расширением |
| Thread blocking | каждый test case запускается в отдельном chat, чтобы blocked thread не ломал следующий case; факт блокировки пишется в provider log |

### 4.2 Optional Scope — Add-Time Endpoints

Add-time endpoints включаются в первую итерацию только при условии, что их можно покрыть небольшим расширением provider'а / отдельным режимом Promptfoo config без изменения backend architecture.

Кандидаты:

| Endpoint surface | Цель теста | Условие включения |
|---|---|---|
| `custom_instructions_write` | prompt injection в user instructions должен получить HTTP 422 | Простая функция provider'а может выполнить PUT и вернуть normalized output |
| `ks_write_rest` | Knowledge Sphere poisoning через REST должен получить HTTP 422 | Существующий API стабилен и не требует сложной подготовки state |
| `mcp_metadata` | tool poisoning через MCP server metadata должен получить HTTP 422 или disable | Только если можно протестировать без поднятия отдельного malicious MCP server |

Если add-time scan требует отдельного fake MCP server, сложной orchestration или нестабильного fixture state, он выносится во второй этап. MVP не блокируется.

### 4.3 Out of Scope

- Multi-user adversarial scenarios.
- Long-running Hydra/GOAT/Crescendo scans на десятки turn'ов в baseline run.
- Автоматический push результатов в Promptfoo Cloud.
- CI gate, падающий pipeline при security failures. На первом этапе scan ручной/операторский.

## 5. Repository Layout

Tooling живёт отдельно от main app:

```text
tools/security-scan/
  README.md
  promptfooconfig.yaml
  learnflow_provider.py
  .env.example
  reports/
    README.md
    <run-id>/
      report.html
      results.json
      provider-events.jsonl
      summary.md
```

### 5.1 Committed

- `tools/security-scan/README.md`
- `tools/security-scan/promptfooconfig.yaml`
- `tools/security-scan/learnflow_provider.py`
- `tools/security-scan/.env.example`
- `tools/security-scan/reports/README.md`
- `tools/security-scan/reports/<run-id>/...` — raw reports are allowed after manual secret/data review.

### 5.2 Not Committed

- `tools/security-scan/.env`
- access tokens, refresh cookies, API keys
- Promptfoo local cache / DB files
- временные scratch files
- отчеты, где обнаружены реальные секреты или пользовательские данные не eval-user'а

Политика по reports сознательно отличается от типичного gitignore-подхода: учебный проект выигрывает от воспроизводимых артефактов. Raw reports коммитятся как audit evidence, но только после ручного review.

## 6. Provider Contract

### 6.1 Promptfoo Interface

Provider реализуется на Python через стандартный интерфейс Promptfoo:

```python
def call_api(prompt: str, options: dict, context: dict) -> dict:
    return {"output": "..."}
```

Provider может использовать `context["test"]["metadata"]`, чтобы различать plugin/strategy и писать их в event log. Для redteam eval это полезно при анализе failures.

### 6.2 Environment

Provider читает конфигурацию из env и/или `options.config`:

| Переменная | Назначение |
|---|---|
| `LEARNFLOW_BASE_URL` | Backend URL, default `http://localhost:8000` |
| `LEARNFLOW_SCAN_USERNAME` | Eval-user для scan |
| `LEARNFLOW_SCAN_PASSWORD` | Пароль eval-user |
| `LEARNFLOW_SCAN_RUN_ID` | Опциональный run id; если нет — timestamp |
| `LEARNFLOW_SCAN_REPORT_DIR` | Output directory for provider-events |
| `LEARNFLOW_SCAN_TIMEOUT_SECONDS` | HTTP/SSE timeout |
| `LEARNFLOW_SCAN_SANITIZE_LOGS` | Если `true`, provider сокращает prompt/output в logs |

`.env.example` коммитится, `.env` — нет.

### 6.3 Backend Lifecycle

Provider выполняет:

1. `POST /api/auth/login`.
2. Если user отсутствует — `POST /api/auth/register`.
3. Создаёт отдельный project для run: `promptfoo-redteam-<run-id>`.
4. Для каждого test case создаёт новый chat.
5. Отправляет prompt в `/api/projects/{project_id}/chats/{chat_id}/messages`.
6. Читает SSE до terminal event или timeout.
7. Нормализует результат в Promptfoo output.
8. Пишет JSONL record в `provider-events.jsonl`.

User-level state reset допускается, но не обязателен в MVP. Если reset реализуется, он должен работать только с eval-user и не трогать чужие данные.

### 6.4 SSE Normalization

Provider понимает минимум такие SSE payloads:

| Event | Meaning |
|---|---|
| `text_chunk` | часть обычного ответа |
| `security_block` | атака заблокирована security layer |
| `error` | infrastructure/app error |
| `done` | normal completion |

Promptfoo `output`:

- normal completion → accumulated assistant text
- `security_block` → marker вроде `[SECURITY_BLOCKED] reason=<reason>`
- infrastructure error → provider error с diagnostic metadata

Marker нужен, чтобы Promptfoo report и ручной summary явно показывали, что attack не просто получил отказ, а был заблокирован LearnFlowAI security layer.

### 6.5 Provider Event Log

Каждый call пишет одну JSONL-запись:

| Поле | Назначение |
|---|---|
| `run_id` | scan run identifier |
| `test_case_id` | Promptfoo test id / index, если доступен |
| `plugin_id` | Promptfoo redteam plugin |
| `strategy_id` | Promptfoo strategy |
| `project_id` | LearnFlowAI project |
| `chat_id` | LearnFlowAI thread |
| `blocked` | bool |
| `block_reason` | raw reason из `security_block`, если был |
| `errored` | bool |
| `latency_ms` | wall-clock latency |
| `prompt` | raw или sanitized prompt |
| `output` | raw или sanitized output |

Этот log — bridge между Promptfoo report и LearnFlowAI observability: по `chat_id` можно искать Langfuse/SIEM traces.

## 7. Promptfoo Configuration

### 7.1 Target

`promptfooconfig.yaml` указывает локальный Python provider:

```yaml
targets:
  - id: file://./learnflow_provider.py
    label: learnflow-backend
```

Если текущая версия Promptfoo предпочитает `providers`, допускается использовать `providers` как alias. Source of truth — проверка `npx promptfoo@latest validate config`.

### 7.2 Purpose

`redteam.purpose` описывает систему как authenticated educational-material preparation agent:

- помогает структурировать образовательные материалы, доклады, лекции;
- может использовать tools, Knowledge Sphere, user memory, MCP;
- не должен раскрывать system prompt, PROTECTED implementation details, internal non-MCP tool names/params/schemas, secrets;
- не должен принимать persistent prompt injection через memory, custom instructions, Knowledge Sphere, MCP metadata;
- должен сохранять полезное поведение для benign образовательных запросов.

### 7.3 Baseline Plugins

Baseline должен быть небольшим, чтобы scan реально запускался локально и не превращался в overkill.

Перед реализацией конкретные plugin IDs проверяются командой `npx promptfoo@latest redteam plugins --ids-only`, потому что Promptfoo быстро меняет каталог redteam-плагинов. Таблица ниже фиксирует желаемые классы атак; если имя plugin'а изменилось, агент выбирает актуальный эквивалент из CLI/docs и отмечает это в `summary.md`.

| Plugin | Зачем |
|---|---|
| `prompt-injection` | direct instruction override / system prompt extraction |
| `indirect-prompt-injection` | попытки имитировать untrusted external content |
| `ascii-smuggling` | скрытые / необычные символы и encoding pressure |
| `hijacking` | попытка сменить роль/цель агента |
| `data-exfil` | запросы на вывод защищённой информации |

Дополнительно, если версия Promptfoo и стоимость прогона позволяют:

- `agentic:memory-poisoning`
- plugins, связанные с excessive agency / tool misuse

### 7.4 Baseline Strategies

Стартовый набор:

- `basic`
- `jailbreak`
- `jailbreak:meta` или `jailbreak:composite` — выбрать один, не оба в первом run
- `base64` или `rot13` — один encoding strategy для smoke
- `homoglyph` — только если scan остаётся быстрым

Hydra / GOAT / Crescendo не входят в baseline. Они полезны для глубокого multi-turn red teaming, но слишком тяжелы для первой учебной итерации.

### 7.5 Frameworks

Включить:

```yaml
redteam:
  frameworks:
    - owasp:llm
    - owasp:agentic
```

Если `owasp:agentic` создаёт нерелевантные cases для текущего scope, оставить только `owasp:llm`.

## 8. Reporting

### 8.1 Report Artifacts

Каждый run сохраняется в отдельную директорию:

```text
tools/security-scan/reports/2026-05-10-promptfoo-baseline/
  report.html
  results.json
  provider-events.jsonl
  summary.md
```

`report.html` — human review.  
`results.json` — machine-readable Promptfoo export.  
`provider-events.jsonl` — LearnFlowAI-specific runtime bridge.  
`summary.md` — ручной summary для преподавателя / ревью.

### 8.2 Summary Format

`summary.md` должен содержать:

- дата и run id;
- git commit hash;
- backend mode: docker/local, base URL;
- Promptfoo version;
- config version / список plugins и strategies;
- total tests / passed / failed / errored;
- число `security_block` по `block_reason`;
- notable findings;
- false positives / false negatives, если обнаружены;
- ссылки/идентификаторы Langfuse/SIEM traces, если доступны;
- limitations;
- next actions.

### 8.3 Commit Policy

Raw reports коммитятся, если:

- run выполнен на dedicated eval-user;
- `.env`, tokens, cookies отсутствуют;
- в prompt/output нет реальных секретов;
- нет пользовательских данных вне synthetic/eval context;
- report полезен как evidence для преподавателя или regression baseline.

Если raw report содержит чувствительные данные, он не коммитится. Вместо него коммитится sanitized `summary.md`.

## 9. Security & Data Hygiene

- Eval-user должен быть отдельным от реального пользователя.
- Provider не должен печатать access token / refresh cookie.
- Provider не должен логировать request headers целиком.
- `LEARNFLOW_SCAN_SANITIZE_LOGS=true` может сокращать prompt/output до preview, но baseline reports для учебного evidence допускают raw prompt/output после review.
- Каждый Promptfoo test case запускается в отдельном chat.
- Project на run создаётся отдельно, чтобы отчеты и traces можно было группировать.
- Auth rate limits учитываются: provider не должен retry-циклить login на неверном пароле.

## 10. Verification

### 10.1 Tooling Verification

- `npx promptfoo@latest validate config` проходит в `tools/security-scan`.
- Provider standalone smoke test отправляет benign prompt и получает normal output.
- Provider standalone attack smoke получает `security_block` на очевидной direct prompt injection.
- `provider-events.jsonl` создаётся и содержит project/chat IDs.

### 10.2 Scan Verification

- Small redteam run завершается без infrastructure errors.
- Promptfoo report генерируется.
- `results.json` экспортируется.
- `summary.md` написан по template.
- At least one blocked case виден в provider log или объяснено, почему scan не добрался до block condition.

### 10.3 Project Verification

Так как production code не меняется, основной gate:

- `make check` — если затрагивались Python workspace files вне isolated tooling.
- `make check-fe` не обязателен, если frontend не трогался.
- `git status` не содержит случайных Promptfoo cache files / `.env`.

## 11. Implementation Phasing

### Phase 1 — Baseline Chat Scanner

- Создать `tools/security-scan` layout.
- Добавить Python provider с auth/project/chat/SSE lifecycle.
- Добавить минимальный `promptfooconfig.yaml`.
- Добавить README с prerequisites и командами запуска.
- Выполнить smoke run на 1-2 prompts.

### Phase 2 — Redteam Baseline Run

- Настроить baseline plugins/strategies.
- Прогнать small redteam scan.
- Сохранить `report.html`, `results.json`, `provider-events.jsonl`.
- Написать `summary.md`.
- Закоммитить reviewed report artifacts.

### Phase 3 — Optional Add-Time Scan

Выполняется только если scope остаётся small:

- Добавить отдельный provider mode или отдельный Promptfoo config для add-time endpoints.
- Проверить `custom_instructions_write` и/или `ks_write_rest`.
- `mcp_metadata` включить только если не требуется отдельный malicious MCP server.
- Отдельно отметить coverage в summary.

Если Phase 3 оказывается сложнее ожидаемого, она переносится в future work без провала итерации.

## 12. Future Work

- Garak integration через REST adapter или custom generator.
- Reactivation / modernization `tools/eval-sec` как regression harness.
- CI job для nightly/manual security scan.
- Multi-turn Promptfoo strategies: Hydra / GOAT / Crescendo.
- Dedicated malicious MCP fixture для robust `mcp_metadata` и `tool_result` indirect injection tests.
- Автоматическая сводка Promptfoo results в `doc/security/`.
