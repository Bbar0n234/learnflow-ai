# Harvest Proposals — feat-009

Кандидаты в backlog / конвенции; landing (запись в `doc/backlog.md` / `doc/tech/conventions.md`) — только после апрува архитектора на pre-commit gate. Ничего ниже туда ещё не записано.

## В backlog

| Кандидат | Тип | Приоритет | Целевая модель / триггер | Проверка «не закрыто» |
|---|---|---|---|---|
| Расхождение автосписка `_list_skill_files` и валидатора пути `file` (`_SAFE_PATH_SEGMENT_RE`, ASCII-only, `rglob` следует симлинкам) — не-ASCII имя модуля или симлинк-наружу видны агенту в футере `load_skill(skill_name)`, но при попытке загрузки дают `Error: invalid file path`, не «not found» | неточность контракта, решение за архитектором | P3 | Развилка на выбор архитектора: (a) расширить листинг `_list_skill_files`, чтобы он пропускал то же, что отклоняет валидатор (`path.is_symlink()`, ASCII-фильтр) — тогда футер листит ровно то, что грузится; (b) зафиксировать в `conventions/agent.md` ограничение «имена модулей скиллов — ASCII, без симлинков» как принятый контракт (скиллы — доверенный контент). Не блокер — на реальных скиллах проекта ненаблюдаемо | Не закрыто: `backend/app/agent/tools/skills.py` на HEAD (`727e145`) — `_list_skill_files` (rglob без фильтра симлинков/charset) и `_SAFE_PATH_SEGMENT_RE` (ASCII-only) по-прежнему рассинхронизированы. Изначально — anytime-запись оркестратора + review-a nit (вопрос) |
| Testcontainers Postgres рвёт соединение в окружении итерации — 34 DB-backed теста (`test_settings_repository.py`, `test_settings_routes.py`, `test_user_memory_routes.py`, `test_mcp_routes.py`, `test_mcp_server_repository.py`, `test_models_route.py`) падают с `psycopg.OperationalError: server closed the connection unexpectedly` | подтверждённый дефект инфраструктуры, вне скоупа диффа feat-009 (диф не трогает БД/миграции) | P2 | Уже воспроизведено — можно брать без дополнительного триггера. Диагностировать первопричину (версия образа Postgres/testcontainers, race в healthcheck, нехватка ресурсов хоста) через `make test-scope P=backend/tests/personalization`; починить или задокументировать обходной путь для локальной разработки | Переверифицировано в этой сессии заново: `make test-scope P=backend/tests/personalization` → `92 passed, 34 errors`, та же сигнатура ошибки (порт testcontainers, «server closed the connection unexpectedly»), прогон вне sandbox (Makefile-таргет). Не эффект sandbox-изоляции сети — воспроизводится и через excluded-от-sandbox путь. `git log` не содержит фикса после введения текущего testcontainers-харнесса. Изначально — anytime-запись оркестратора |
| Sync I/O (`read_text`, `rglob`+`is_file`+`resolve`) внутри `async def load_skill` блокирует event loop | known-debt, принятое следствие (пренебрежимо при текущем размере скиллов) | P3 | Триггер: появление крупных скиллов или высокая конкурентность вызовов `load_skill` → обернуть файловые операции в `asyncio.to_thread`. Не действие сейчас | Не закрыто — паттерн подтверждён чтением кода на HEAD; диф T1.1/T1.2 добавил ещё sync I/O (обход директории) тем же паттерном, что уже был в модуле до итерации (review-a, pre-existing) |

## В конвенции (conventions.md)

Кандидатов нет. Решения итерации (allowlist-паттерн вместо blocklist, `as_posix()` для стабильности путей, module-level хелперы без состояния, симметрия ошибок «not found») специфичны для `load_skill` и уже задокументированы на нужном уровне в `doc/tech/agent-runtime.md` — обобщать их в репозиторный конвеншен не за что: ни один не встретился второй раз в другом домене кода за итерацию.

## known-trivial (не в backlog, фиксируем как известное)

Нет. Оба мелких nit'а с реальным дефектом (review-a A1 — непокрытая тестом ветка symlink-эскейпа; review-a A3 — несимметричная диагностика в отказных ветках валидации пути) исправлены в самой итерации (коммит `bbc417b`) — не дожили до harvest как долг.

## Отсеяно как шум (с причиной)

- **review-b nit 1 (`skills/tech-article-writing/SKILL.md:6`, связка «Используй когда нужно:» vs «Используй когда:»).** Осознанное «не делаем» — адъюдицировано архитектором ещё на фазе плана (`tracks/T2/plan.md` § Open Questions №1) и подтверждено в T2 summary: конвенция задаёт паттерн, не посимвольный шаблон, менять `conventions/agent.md` не требуется.
- **review-b nit 2 (`_list_skill_files`, dotfile-исключение — «любой сегмент с `.`» шире формулировки «dotfiles»).** Дрейф документации, исправленный на месте в этой же итерации: `doc/tech/agent-runtime.md:239` уже содержит уточнение «скрытым считается любой сегмент относительного пути, начинающийся с `.`, не только имя файла».
- **review-a A1 (непокрытая тестом ветка symlink-эскейпа второго слоя защиты).** Исправлено в итерации — `test_load_skill_file_rejects_symlink_escape` добавлен, коммит `bbc417b`.
- **review-a A3 (отказные ветки валидации пути без списка `Available files`).** Исправлено в итерации — обе ветки (`_is_safe_relative_path` отказ и `is_relative_to` отказ) теперь симметричны ветке not-found, коммит `bbc417b`.
- **Судьба `author-voice/` (профиль голоса) и judge-проходы независимым субагентом, упомянутые в T2 summary как «оставлено как есть».** Не хвост feat-009 — уже запланированы отдельными итерациями (`doc/tasks/tasklist-post-mvp.md`: feat-012 — хранилище профиля голоса, feat-011 — субагенты/judge); дублировать в backlog запрещено инструкцией harvester'а.
