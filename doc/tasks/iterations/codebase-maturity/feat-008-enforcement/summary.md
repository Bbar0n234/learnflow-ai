# Summary: feat-008 — Enforcement & надёжность петель обратной связи

## Что сделано

Итерация выросла из исходного «enforcement кода» в **надёжность петель обратной связи во всём процессе** (зафиксировано в [design-brief.md](design-brief.md)). Общий знаменатель — ничто ценное не теряется: ни арх-нарушение, ни хвост-долг, ни регрессия после фикса. Доставлены три блока + предварительный research.

### Предшаг — Deep research по code review
13 источников (Anthropic Claude Code, OpenAI Codex, Copilot, CodeRabbit, Greptile, Google eng-practices, Conventional Comments и др.) → [research-code-review.md](research-code-review.md). Дал каркас режима A (классы A-E), severity-модель (`blocker/nit/pre-existing` + ось намерения), и эвристику границы: *детерминированно — всё, для чего достаточно увидеть форму кода; LLM — всё, для чего нужно понять смысл*. Прямо подтвердил двухрежимный дизайн (вендоры строят ревью как узко-сфокусированных агентов + шаг верификации).

### Блок 1 — Enforcement-ревью (детерминированное + LLM)
**Arch-checker** (детерминированный, разгружает ревьюеров): 9 контрактов import-linter (слои backend/siem, `api/routes ↛ repositories/agent`, транспорт-в-домене, изоляция `packages/`), 3 AST-ассерта (`tools/arch-checker/`: порядок middleware, зеркала `problem.py`, узкий module-singleton), eslint-plugin-boundaries (FSD-границы). Системный **реестр инвариантов** — [arch-checker.md](../../../../tech/arch-checker.md): исчерпывающий проход по конвенциям с пометками «покрыто / кандидат / → LLM-reviewer». В gate: `make check` / `make check-fe` + pre-commit + CI.

**Два LLM-ревьюера** в фазе CODE_REVIEW (`.claude/skills/aidd-orchestrator/prompts/reviewer-{a,b}.md`): режим A (качество кода — баги/сложность/читаемость) и режим B (соответствие контракту — конвенции/doc-first/архитектура). Параллельно, read-only, в разные файлы; severity `blocker/nit/pre-existing` + verification bar (blocker только с `file:line`). Конфликт A↔B разруливает implementer, неразрешимый → эскалация.

### Блок 2 — Harvest
Роль `harvester` + фаза HARVEST в FSM: незакрытые долги и кандидаты в конвенции собираются по рубрике в `harvest-proposals.md` (anytime + конец итерации), проходят проверку «не закрыто ли уже» (grep + git log) и гейт архитектора. Канон секции `## Follow-ups` в summary. Диагноз из прогона по 7 summary: дисциплина почти есть (24/40 хвостов уже отслеживались), течёт узкий хвост — лечится гейтом + каноном формата.

### Блок 3 — Реформа конвенций
- **Рычаг-1 (плотность):** § Enforcement добавлен; лёгкое уплотнение прозы при дроблении (без потери «почему» и норм).
- **Рычаг-2 (дробление):** монолит `conventions.md` → ядро + `conventions/{db,api,agent,frontend}.md`, подгрузка по домену. Решение — ADR-025.
- **Рычаг-3 (удаление норм, ушедших в checker):** **отложен явно** — defense in depth на период обкатки arch-checker'а.

### Сквозное
Норма ре-верификации (правка кода аннулирует зелёный статус затронутого; детерминированный гейт — всегда, ручные кейсы — затронутая область). Формат тест-кейсов run-log + шаблон `_templates/test-cases-template.md` с инлайн-конвенциями.

## Отклонения и нюансы

- **Скоуп расширился** по ходу проработки (harvest, ре-верификация, тест-кейсы, два ревьюера вместо одного) — по решению архитектора, ничего не откладывали сверх явно вынесенного в feat-009/backlog.
- **R1-нарушения не чинились.** Все три (settings/mcp_servers/feedback → repositories напрямую) нетривиальны (нет готового сервиса для механической делегации) → allowlist в контракте + карточки в backlog ([harvest-proposals.md](harvest-proposals.md)). По дизайну: feat-008 про *механизм*, не про разгребание долга.
- **`isolation: worktree` подсунул устаревшую базу.** Изолированный worktree для arch-checker ответвился от `e9bb742` (76 коммитов позади develop, без error-handling архитектуры). Агент корректно остановился и эскалировал. Воркэраунд: явный соседний worktree off develop. Зафиксировано как known-trivial в harvest-proposals.
- **Security-баг feat-006 (`security_block` зависание) — фантом.** Расследование показало: закрыт в feat-005 коммитом `3141097` (корень — row-lock `thread_views`, не `aupdate_state`). В backlog не заведён. Урок усилил рубрику harvest (проверка «не закрыто ли уже»).
- **`logging.getLogger`** не стал чистым grep-правилом: благонадёжный match (подавление `opentelemetry.context` в `infra/langfuse.py`) → помечен `→ LLM-reviewer` в реестре.

## Верификация

- `make check` — зелёный: ruff + mypy (включая `tools/arch-checker`) + import-linter (**9 контрактов, 0 broken**) + AST-ассерты.
- `make check-fe` — зелёный: tsc + eslint (с FSD-boundaries) + prettier.
- **Sanity (чекер кусается):** временный запрещённый импорт `api/routes → repositories` → import-linter `BROKEN` (8/1); откат → 9/0. AST-ассерты независимо проверены агентом на синтетических нарушениях.
- LLM-ревьюеры и harvester — статические артефакты (промпты/роли); реальный прогон на живой итерации — естественная верификация в эксплуатации.

## Артефакты

- [design-brief.md](design-brief.md) · [research-code-review.md](research-code-review.md) · [harvest-proposals.md](harvest-proposals.md)
- [arch-checker.md](../../../../tech/arch-checker.md) (реестр инвариантов) · ADR-025 (формат конвенций)
- Промпты: `.claude/skills/aidd-orchestrator/prompts/{reviewer-a,reviewer-b,harvester}.md`; FSM — `SKILL.md`
- `tools/arch-checker/`, шаблон `doc/tasks/iterations/_templates/test-cases-template.md`

## Follow-ups

Кандидаты на апрув — в [harvest-proposals.md](harvest-proposals.md): 3 R1-сервиса (extraction), доподключение кандидат-правил arch-checker, known-trivial по `isolation: worktree`.
