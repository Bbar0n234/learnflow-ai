# Run-log · Ф2a Conventions

Журнал фазы написания тест-конвенций. Версионируемый дрибл контекста: автор → ревью → фикс.
Формат: что сделано, что нашли, что решили. Не дублирует conventions — фиксирует ход работы.

## Шаг 1 — автор (Opus)

Создан `doc/tech/conventions/testing.md` + строка в указателе `doc/tech/conventions.md`.
Разделы: модель (что/чем тестируем), структура/нейминг, async/pytest, HTTP, тестовая БД, фейки LLM/guard,
дубли, граница unit/eval, фабрики, coverage/DoD, frontend, антипаттерны, целостность (A6), два чек-листа.
Ссылки на db/api/agent/frontend вместо дублирования. Автор вынес незакрытый шов: интеримный раздел
`## Тестирование` в ядре не трогал (реконсилировать когда приземлится инфра).

## Шаг 2 — ревью (2 независимых агента Opus, adversarial)

### Ось «полнота и фактическая точность» (против decisions + кода)
Подтверждено корректным: шов `build_graph(model=)` / `LLMClassifier(llm=)` инъектируем; вердикты
CLEAN/SUSPICIOUS/INJECTION; classifier парсит `str(content).strip().upper()`; guard-фейк = плоский
`AIMessage`; savepoint-режим и pytest-asyncio 1.x — верны. Найдено:
- **F1 (major)** «SUSPICIOUS → warning/redact» неверно: SUSPICIOUS только лог-warning, проходит; редакция/блок только на INJECTION (`runtime_security.py:93,96-103,128,156`, `graph.py:160,325`).
- **F2 (minor)** конфляция слоя действий (INJECTION-only) с `VERDICT_TO_LEVEL` (observability, `types.py:55`).
- **F3 (major)** шов в `GraphFactory` подан как существующий; в коде `graph_factory.py:52` создаёт модель инлайн — параметр вводит эта итерация (C1 вариант а).
- **F4 (major)** S1 rate-limit: нет указаний тестировать как unit с инъекцией монотонных часов (`infra/rate_limit.py`, in-memory, не Redis).
- **F5 (major)** S8: выпала cross-side проверка (эмиттер+консьюмер на один словарь), осталась внутренняя. Layout: `packages/siem-contracts/siem_contracts/` без `src/`.
- **F6 (minor)** не упомянут Hypothesis для чистых функций (E1).
- **F7 (minor)** не покрыта ветка classifier: невалидный ответ → ретраи → degrade-to-CLEAN (`classifier.py:99-135`, фейк с невалидной строкой).
- **F8 (minor)** таблица: guard-стаб отдаёт `GuardResult`, не голый `Verdict`.
- **F9 (minor)** нет строки таблицы под SIEM event parsing/ingest.

### Ось «ясность и single-source»
Подтверждено: делегирование доменных норм без дублей; чек-лист автора исполним почти целиком;
feat-маркеров внутри testing.md нет. Найдено:
- **B-M1 (major)** ядро `## Тестирование` конфликтует с новой нормой + содержит feat-009-маркеры (нарушение CLAUDE.md) → реконсилировать на месте, ссылка из testing.md должна вести на стабильный регламент.
- **B-M2 (major)** «БД реальная или fake-сервис» без критерия выбора.
- **B-M3 (major)** DoD-гейт «service vs glue» без операциональной границы.
- **B-M4 (major)** висячий `(A6)` в чек-листе ревьюера — кода нет в документе.
- **B-m2/m3/m4 (minor)** прод-детали реализации в § Фейки (риск дрейфа); «желательно/по ситуации»; xUnit-теория как объёмный жирок.
- **B-B1 / m1** `make test-fe` и `packages/testing` — forward-refs; материализуются в Ф2b (не дыра).

## Шаг 3 — фикс (Opus)

Сведённый список из 16 правок передан фикс-агенту (правит `testing.md` + реконсилирует ядро
`conventions.md ## Тестирование`). Forward-refs (`make test-fe`, `packages/testing`) оставлены —
их доставляет Ф2b. Результат фикса — ниже.

Все 15 правок внесены и сверены с кодом (`runtime_security.py`, `types.py`, `classifier.py`, `guard.py`,
`graph_factory.py`, `rate_limit.py`, импорты `siem_contracts` на обеих сторонах). Ключевое:
- Guard-семантика исправлена на верную: блок/редакция строго по `INJECTION`; `SUSPICIOUS` → лог-warning + Langfuse WARNING, проходит без редакции; `CLEAN` → пропуск.
- Слой действий и `VERDICT_TO_LEVEL` разведены как два слоя.
- Шов в `GraphFactory` описан как норма тестового шва (инъектируемая model-factory), без ложного «параметр уже есть».
- Добавлены: rate-limit как unit с инъекцией часов; SIEM cross-side contract-drift + строка таблицы под ingest; Hypothesis для чистых функций; второй фейк classifier (невалидная строка → degrade-to-CLEAN); guard-стаб → `GuardResult`.
- DoD: операциональный признак glue; критерий «БД реальная/fake под handler».
- Ядро `## Тестирование` реконсилировано (интерим → норма), feat-маркеры убраны (grep чист).
- Висячий `(A6)` → ссылка на § Целостность тестов.

Орк-сверка финального `testing.md`: документ цельный, по каждому скоупу S1–S9 есть ориентир, чек-листы
исполнимы. **Конвенции заморожены** (Ф2a done). Forward-refs (`make test-fe`, `packages/testing`,
`packages/siem-contracts/tests`) материализует Ф2b.

## Итог Ф2a
Артефакты: `doc/tech/conventions/testing.md` (новый), `doc/tech/conventions.md` (указатель + реконсиляция
ядра). Гейт архитектора: вынесено как чекпойнт, исполнение не блокируется — Ф2b стартует.
