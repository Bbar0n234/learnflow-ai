# Harvest Proposals — feat-008 Enforcement

Кандидаты на апрув архитектора (pre-commit gate). Перенос в `backlog.md`/`conventions.md` — только после апрува. Каждый backlog-кандидат прошёл проверку «не закрыто ли уже».

## В backlog

| Кандидат | Тип | Приоритет | Целевая модель / триггер | Проверка «не закрыто» |
|----------|-----|-----------|--------------------------|------------------------|
| **R1: `SettingsService` — вынести `api/routes/settings.py` из прямого доступа к `repositories/settings.py`** | tech-debt | P3 | Нет сервиса; `ModelConfigResolver.resolve(repo, …)` берёт репозиторий параметром. Перенос = проектирование сервиса, не замена. Триггер активации: когда роут трогается по другой задаче | вскрыто arch-checker'ом feat-008, в allowlist `ignore_imports`, не закрыто |
| **R1: `McpServerService` — read-path методы; `api/routes/mcp_servers.py` (18 хендлеров) ходят в репозиторий напрямую** | tech-debt | P3 | Сервис покрывает только write/guard-flow; добавить read/list/toggle/delete методы | в allowlist, не закрыто |
| **R1: `FeedbackService` — выделить из `api/routes/feedback.py` (инлайн Langfuse + Redis TraceStore + ownership)** | tech-debt | P3 | Нет сервиса; выделение сервисного слоя | в allowlist, не закрыто |
| **Доподключить детерминированные кандидат-правила arch-checker** | tech-debt / tooling | P3 | Реестр `arch-checker.md` помечает как «кандидат» (нарушений нет, подключаются без разгребания долга): `no-console` eslint (frontend), ruff `DTZ` (`datetime.utcnow`), AST/grep на `String(n)`/`Column()` в моделях. Триггер: при желании ужесточить gate | новые правила, не существуют |
| **arch-checker правило: каждый workspace-member из корневого `pyproject` bind-mount/COPY'ится в каждый Dockerfile** | tech-debt / tooling | P3 | Детерминированно проверяемый инвариант. CI feat-008 упал: `tools/arch-checker` добавлен в workspace, но не в Dockerfile'ы → `uv sync --locked` падает. Починено вручную; AST/парс-правило ловило бы класс на корню. Стыкуется со smoke-boot из feat-009 | пофикшено в feat-008 (Dockerfile), правило — новое |
| **Нестыковка: `decisions.md` используется (3 промпта ролей), но не в canonical structure `workflow.md`** | drift / doc | P3 | `decisions.md` эмпирически бывает (feat-007), на него ссылаются harvester/sofa-contributor «если есть», но структура артефактов итерации в `workflow.md` его не описывает и FSM не производит. Решить: легализовать как опциональный артефакт или убрать ссылки | выявлено adversarial-ревью feat-008, не закрыто |

## В конвенции (conventions.md)

Нет отдельных кандидатов: конвенции feat-008 (§ Enforcement, ре-верификация, дробление) внесены прямо в рамках итерации. Реестр `arch-checker.md` фиксирует, какие нормы детерминированы.

## known-trivial (не в backlog, фиксируем как известное)

- **`Agent(isolation: "worktree")` может ответвить worktree от устаревшей базы.** В feat-008 изолированный worktree для arch-checker ответвился от `e9bb742` (76 коммитов позади develop, без error-handling архитектуры) вместо актуального `develop` — агент корректно остановился и эскалировал. Воркэраунд: для делегирования код-работы создавать **явный** соседний worktree off `develop` (`git worktree add -b <branch> ../<dir> develop`), а не полагаться на `isolation: worktree`. Не баг нашего кода — gotcha инструмента; фиксируем как операционную заметку для будущих делегирований.

## Отсеяно как шум (для прозрачности гейта)

- `logging.getLogger("opentelemetry.context").setLevel(...)` в `infra/langfuse.py` — благонадёжное подавление стороннего логгера, не нарушение «только structlog». Реестр помечает класс как `→ LLM-reviewer` (чистый grep дал бы ложное срабатывание). Не долг.
- Зомби-worktree от смерженных feat-002…006 и от isolation-прогона — операционная уборка архитектора, не задача.
