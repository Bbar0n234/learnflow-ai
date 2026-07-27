# Harvest proposals — feat-002-chat-ux

Финализирует harvester на фазе HARVEST. До того — anytime-записи оркестратора.

## Anytime-кандидаты (оркестратор)

- **Глобальный скилл `~/.claude/skills/aidd-orchestrator` устарел относительно проектного `.claude/skills/aidd-orchestrator`** (нет фаз PLAN_REVIEW / TEST_AUTHORING / TEST_REVIEW / GREEN, декларирует «один сабагент за раз» против fan-out по партиции). Обнаружено ревьюером партиции feat-002: slash-команда подтянула глобальную версию, оркестратор вручную переключился на проектную. Кандидат: синхронизировать/удалить глобальную копию, чтобы slash-команда резолвилась в проектный скилл. Тип: конвенция/инфраструктура процесса.
- **Уточнение конвенции env-переменных** (решение архитектора на эскалации feat-002): правило «atomic change четырёх мест» читать как «`.env.local.example` — только для значений, реально переопределяемых в local dev» — прецедент `LLM_IMAGE_TIMEOUT_SECONDS` и `LLM_TITLE_TIMEOUT_SECONDS` (три места). Кандидат: поправить формулировку в CLAUDE.md § Жёсткие правила и `conventions.md` § Что попадает в env. Тип: конвенция.
- **`ProjectCreate.name` без лимита длины** — дрейф-фикс feat-002 ограничил `ProjectUpdate.name` (по брифу), но `ProjectCreate.name` (`backend/app/api/schemas/projects.py`) остаётся без лимита: POST проекта разрешает имя длиннее, чем PUT. Обнаружено plan-review T1; в scope брифа не входит — не расширяли. Кандидат в backlog: распространить общую константу лимита. Тип: дрейф API-валидации.
- **Расхождение локализации UI**: новые компоненты чата (ChatActions, модалка выбора проекта) — русские по мокапу feat-002, соседние `ProjectActions`/`CreateProjectModal` — английские («Rename», «Delete», «New Project»). Кандидат в backlog: единая локализация project-компонентов. Тип: UX-долг.
