# Summary: feat-009 — Testing: Philosophy + Coverage

Завершающая итерация фазы codebase-maturity: с нуля построена тестовая культура и инфраструктура проекта, покрыта кодовая база, роли встроены в оркестратор.

## Что сделано

### Фаза 0 — Discovery + теория (фундамент)
Перед написанием тестов — глубокое изучение основания (deep research + сабагенты, не только параметрические знания): модели тестирования (пирамида/трофей/honeycomb, solitary vs sociable, test doubles, Google sizes), async/pytest-asyncio, тестовая БД, тестирование LLM/agent-путей, TDD и reward hacking, разбор внешних скиллов. Материал — `theory/00-07`, решения — `decisions-phase1.md`, план — `plan.md`.

### Ф2a — Тест-конвенции (convention-first)
`doc/tech/conventions/testing.md` — что и чем тестируем, async, тестовая БД, фейки LLM/guard, граница unit/eval, coverage-политика (branch + ratchet, без числового floor), антипаттерны, A6-целостность + чек-листы автора и ревьюера. Прошёл два adversarial-ревью + фикс по 15 находкам. Ядро `conventions.md` реконсилировано (убран интеримный режим и feat-маркеры).

### Ф2b — Тест-харнесс (инфраструктура, заморожен)
`packages/testing` + conftest-иерархия: шов модели в `GraphFactory` (инъектируемая model-factory; прод не меняется), testcontainers-Postgres + `alembic upgrade head` + транзакционный откат + отдельная БД на воркер под xdist, страж дрейфа модель↔миграции, аутентифицированный async-клиент, фейки LLM (`GenericFakeChatModel` с tool_calls) и guard (`StubGuard`), фабрики данных, SSE-хелперы, smoke-boot, Redis-фикстура, фронтовый Vitest/RTL/MSW. Прошёл adversarial-ревью (до заморозки выловлены мёртвый xdist и footgun одной сессии — закрыты).

### Ф3 — Покрытие (веер из 9 вертикальных скоупов)
~700 тестов, по одному агенту на скоуп: S1 auth, S2 guard, S3 agent-runtime, S4 projects, S5 chat/SSE, S6 sphere, S7 personalization, S8 SIEM+contracts, S9 frontend. Прод-код под тесты не правился (A6); реальные баги задокументированы как `xfail`/находки.

### Ф4 — Adversarial-ревью (9 ревьюеров, по одному на скоуп)
«Зелёное ≠ хорошее»: каждый ревьюер бил тесты против конвенций и чек-листов. Вскрыто **~10 реальных прод-дефектов** (несколько security/user-facing) + слабые/тавтологичные тесты + кросс-скоуповая слабость `StubGuard`. Все находки — в `runlog/review-findings.md` (реестр с severity и владельцем фикса).

### Ф5 — Доведение до зелёного
- **Ф5a (харнесс):** аддитивно обогащён `StubGuard` (`detection_layer`, `call_records`), `bind_tools` фейку, Redis-фикстура, siem-contracts в гейт.
- **Ф5b (прод-баги, мини-оркестратор):** P1 (SSE error-payload `message`→`detail`), P2 (auth 500→401 на битом `sub`), P3 (SSRF-bypass: ipv4-mapped/0.0.0.0/CGNAT), P4 (/test тип исключения), P5 (DELETE идемпотентность), P6 (SIEM не-JSON poison-drop), P9 (a11y label↔input), P10 (contained: запрет редиректов). Каждый — фикс прода + развёрнутый валидирующий тест + независимое ревью.
- **Ф5c (усиление, 8 backend-скоупов + S9):** +69 backend + 42 frontend тестов по находкам ревью (контракты mid-stream через `call_records`, reason через `detection_layer`, `_reduce_context`, security_block-ветки раннера, payload трейсинга, tool-streaming, eager-load через `expunge_all`, продовый SSE-словарь, НЕноминальный cross-side контракт, Select-взаимодействие, SSE-глубина, добор слайсов security/user-settings). Попутно починены a11y/DOM-дефекты новых слайсов.
- **Ф5d (гейт):** xdist-баг (`uuid4()` в parametrize) пойман и закрыт. Полный прогон зелёный серийно и под `-n2`.

### Ф6 — Встройка в оркестратор + CI
`.claude/skills/aidd-orchestrator`: роли **test-author / test-reviewer / fixer** (single-source — ссылки на `testing.md`), FSM `IMPLEMENT → TEST_AUTHORING → TEST_REVIEW → GREEN (fixer≠автор) → ручной хвост`, секции A6-guardrails и журналирования. CI: снят `continue-on-error` со `make test`, добавлен гейт `make test-fe`.

## Отклонения и нюансы
- **Параллелизация (override архитектора).** Дефолтное правило оркестратора «один сабагент за раз» сознательно снято на эту итерацию: Ф3/Ф4/Ф5 шли веером (9 скоупов) и через Workflow-мини-оркестраторы. В оркестратор параллель НЕ форсилась в дефолтный FSM — осталась опцией под явный опт-ин.
- **Прод-баги починены в тест-итерации (решение архитектора).** Не планировалось, но ~10 дефектов, найденных ревью, дешевле починить сразу (тесты уже написаны). Глубокие/дизайн-зависимые — в backlog.
- **Кросс-скоуповый фикс `StubGuard`** закрыл одну находку (S2/S6/S7) единым изменением харнесса.

## Верификация
- `make check` (ruff + mypy ×3 + import-linter + arch-checker) — GREEN.
- `make test` — backend **589** / siem **21** / contracts **64** passed.
- `make test-fe` — **120** passed (22 файла).
- `make test-parallel` (`-n2`, контейнер на воркер) — GREEN.
- `make check-fe` — GREEN. Branch-coverage backend — **78%** (с ~0 базы; baseline для ratchet).

## Артефакты
- `doc/tech/conventions/testing.md` (+ реконсиляция ядра `conventions.md`).
- `packages/testing/` (харнесс), conftest-иерархия, фабрики, фейки, SSE-хелперы, Redis-фикстура.
- Тесты: `backend/tests/<scope>/`, `services/siem-service/tests/`, `packages/siem-contracts/tests/`, фронт-колокация.
- `theory/00-07`, `decisions-phase1.md`, `plan.md`, `runlog/*` (per-scope run-log'и, `infra*.md`, `review-findings.md`).
- Оркестратор: роли `test-author/test-reviewer/fixer`, обновлённый SKILL.md; CI-гейт.

## Follow-ups
В `doc/backlog.md` (секция «feat-009 follow-ups»): полная защита от DNS-rebinding (resolve-and-pin transport, P10), типизированный `emit_security_event` (D2), Protocol'ы для repo/trace_store фейков (D3), Playwright e2e/visual-regression, LLM-eval контур (Langfuse datasets), mutation testing, проектный testing-skill, дрейф контракта `security_block` SSE, антипаттерн «нет `uuid4()` в parametrize». Эскалация P7 (мёртвый код SIEM) разрешена: намеренно по ADR-020 (оставлено + комментарий).

**Синхронизация (вне ветки):** user-level копия `~/.claude/skills/aidd-orchestrator/` устарела — нужен полный ресинк версионированной.
