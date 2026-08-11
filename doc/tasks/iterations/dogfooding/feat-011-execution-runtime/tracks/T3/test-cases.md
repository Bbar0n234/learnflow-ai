# Test Cases: feat-011 — Execution runtime / трек T3 (executor-сервис)

Трек поднял новый сервис `services/executor/` — тупой исполнитель джоб: принимает `POST /jobs`,
запускает команду внутри `unshare`+`bwrap`-песочницы под жёстким deadline и возвращает
`{stdout, stderr, exit_code}`. Всё это новое поведение, регрессировать нечему; кейсы страхуют
контракт, на который завязан backend (T1), и границы изоляции, ради которых сервис существует.

Набор делится ровно по одной линии: **что можно проверить, не запуская bwrap** — автотесты
(`services/executor/tests/`, 87 кейсов), и **что без реальной песочницы не проверяется в
принципе** — смоук образа (`make smoke-executor`) плюс ручные кейсы ниже. Причина линии
техническая: bwrap требует непривилегированных user namespaces, недоступных в агентской и
CI-песочнице, а поведение сети внутри пустого netns отличается между реальным ядром
(`ENETUNREACH`) и gVisor (`EAFNOSUPPORT`) — автотест на этом либо не запустится, либо
зафиксирует не тот инвариант. Поэтому автотесты проверяют **argv, который получит bwrap**, и всю
логику вокруг него (резолв workspace, deadline, kill, потолок вывода, HTTP-контракт, knobs), а
фактическую изоляцию проверяет смоук внутри собранного образа.

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (прод-VM, UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры**: `📊` — проверка наблюдаемости (JSON-логи контейнера, Langfuse-спан джобы); `🔴` — проверка границы изоляции / атаки; `[auto]` — кейс закрыт автотестом; `*(регресс)*` — кейс страхует «поведение не сломалось».
- **run-log** (только у перепрогнанных кейсов) — строка-история флипов с причиной:
  `runs: r1 ✅ → r2 ❌ (после фикса review #3) → r3 ✅`. Один прогон — run-log не нужен.

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`, executor-строка `make test`) — перепрогон всегда; смоук образа — перепрогон при любой правке `services/executor/**` или Dockerfile (образ пересобрать: `make docker-build-executor`). Каждый перепрогон → запись в run-log.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики: не сошлось — повтори (мог быть транзиент); не сошлось второй раз — fail + эскалация, без долгой отладки. Инструменты: JSON-логи executor'а в stdout контейнера (`docker logs` / `docker compose logs executor`), `docker inspect`, `ps`/`pgrep` внутри контейнера, вывод `make smoke-executor`. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer**, не сам тестировщик.

**Скоуп по трекам.** Кейсы с префиксом `{T3.x}` гоняются на треке T3 (нужен только собранный образ, compose не нужен) + Layer 0; cross-cutting без префикса — в INTEGRATION_TEST на живой топологии. Не пропускать кейсы молча — неприменимый помечать причиной.

### Процесс (тестировщик поднимает стенд сам)

1. Трековые кейсы (`{T3.x}`): `make docker-build-executor`, затем `make smoke-executor [RUNTIME=runc|runsc]`. Ни БД, ни Redis, ни compose executor'у не нужны — сервис не имеет ни зависимостей, ни состояния.
2. Cross-cutting кейсы: полная топология `make docker-up` (после того, как T1 внёс блок executor'а и сеть `exec` в compose), проект с workspace на общем volume, ход агента через UI.
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в run-log + `## Решения и обоснования` summary трека.
4. После прогона — сводка (pass / failed / **deferred**). Deferred — кейсы 👤/заблокированные (нет прод-VM с runsc, не готов compose-блок T1): отдельным счётчиком + причина по каждому.

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Executor HTTP | `http://executor:8002` изнутри сети `exec` (наружу порт не публикуется); `docker run -p` для ручных прогонов |
| Логи executor'а | JSON-строки в stdout контейнера: `docker logs <id>` / `docker compose logs executor` |
| Изоляция / runtime | `docker inspect`, `ps`/`pgrep` внутри контейнера, вывод `smoke_sandbox.py` |
| Файлы джобы | общий volume workspaces (`/workspaces/<project_id>` внутри контейнера) |
| Тулчейн образа | `make smoke-executor`, шесть сценариев `services/executor/smoke/` |

---

## Дизайн автотестов

**Покрываем автотестом** — 87 кейсов в `services/executor/tests/`, раскладка по подсистемам сервиса.
Все они гоняются executor-строкой `make test` и не требуют ни БД, ни сети, ни Docker.
Общий харнесс — `tests/conftest.py`: фабрика `Settings` на временных корнях, фабрика
ASGI-клиентов поверх свежего `create_app()` (подмена настроек через `app.dependency_overrides` —
тот же шов `SettingsDep`, которым пользуется хендлер), плюс изоляция двух кусков глобального
состояния, которые сервис трогает: переменных `EXECUTOR_*` и конфигурации structlog. Джобы в
тестах запускаются **без песочницы** (`sandbox_enabled=False`) — см. границу авто/ручное ниже.
Из `packages/testing` ничего не берётся осознанно: тамошние утилиты — про Postgres, LLM-фейки и
SSE, у executor'а нет ни того, ни другого, ни третьего.

Изоляция логов держится на публичном API structlog: `reset_defaults()` плюс выдача модулям
свежих прокси (`module.logger = structlog.get_logger()`) — прокси, который ещё ни разу не
использовали, по определению ничего не закэшировал, поэтому лезть в представление кэша
внутри structlog не нужно. Это существенно для отрицательных лог-ассертов («предупреждения не
было»): логгер, закэшированный под прошлым `create_app()`, ушёл бы от `capture_logs` и красил
такие кейсы вакуумно. Async-движок — общий для монорепо `asyncio_mode = "auto"` в
`services/executor/pyproject.toml` (`conventions/testing.md` § Async): `async def`-кейсы
подхватываются без ручного `@pytest.mark.asyncio`, как в backend и siem-service.

### `test_settings.py` — конфигурация сервиса

1. **Файл**: `tests/config/test_settings.py` — solitary-unit, без дублей (шов — переменные окружения через `monkeypatch`)
2. **Тестирует**: `executor.config :: Settings`
3. **Суть**: Суита фиксирует восемь `EXECUTOR_`-knobs дословно — имена, дефолты и то, что сервис читает только свой префикс. Она страхует от тихого расхождения с compose и `.env*.example`, которые пишет соседний трек: переименованное поле или изменённый дефолт ничего не сломали бы при старте, сервис просто работал бы на своих значениях, пока эксплуатация думает, что применилось значение из compose. Отдельным кейсом закреплено, что песочница включена по умолчанию — dev-escape-hatch должен открываться намеренно, а не доставаться из-за незаданной переменной.
4. **Кейсы**: дефолты равны таблице knobs; `sandbox_enabled` по умолчанию `True`; каждая из восьми `EXECUTOR_*`-переменных читается и приводится к типу (parametrize); переменная без префикса (`LOG_LEVEL`, `MAX_TIMEOUT_SECONDS`) игнорируется.

### `test_build_job_argv.py` — префикс песочницы

1. **Файл**: `tests/sandbox/test_build_job_argv.py` — solitary-unit на чистой функции, без дублей
2. **Тестирует**: `executor.sandbox :: build_job_argv`
3. **Суть**: Суита читает argv как декларацию изоляции: чем джоба владеет, чего в её мире вообще не существует и чем её убивают. Она страхует три вещи, которые ломаются молча и вскрываются только на проде — потерю любого из трёх флагов kill-контракта (джоба или её внуки переживают deadline), возврат к родному `--unshare-net` bwrap (фатален под gVisor) и перестановку `--ro-bind` исходника перед `--tmpfs /tmp` (tmpfs накрывает файл, и ветка `code` перестаёт находить собственный исходник). Флаги проверяются **по позиции**, а не по вхождению в argv: уехавший за `--` флаг перестаёт настраивать песочницу и становится аргументом самой джобы — изоляции нет, слово в argv есть, и ассерт `flag in argv` этого не отличит. Отдельно закреплено, что выключенная песочница кричит об этом на каждую джобу, а не один раз при старте.
4. **Кейсы**: команда доезжает без изменений после `--`; сеть режется внешним `unshare -U --map-current-user -n`, `--unshare-net` в argv отсутствует; каждый из `--unshare-pid` / `--die-with-parent` / `--new-session` лежит в сегменте `bwrap … --` (parametrize, срез `argv[argv.index("bwrap") + 1 : argv.index("--")]`); единственный rw-бинд — свой workspace, соседний проект в argv не упоминается, `--chdir /workspace`; `/skills` монтируется ro; тулчейн (`/usr`, venv из `sys.prefix`) ro, плюс `--proc`/`--tmpfs /tmp`; все источники бинд-маунтов существуют на хосте (иначе bwrap падает на старте); `--clearenv` в том же сегменте плюс ровно пять `--setenv` (PATH/HOME/LANG/MPLCONFIGDIR/XDG_CACHE_HOME), env сервиса в argv не протекает; `extra_ro_binds` вставляются после `--tmpfs /tmp`; выключенная песочница возвращает голую команду (копию, не тот же список) и пишет WARNING на каждый вызов; включённая — не пишет.

### `test_resolve_workspace.py` — резолв `project_id` в директорию

1. **Файл**: `tests/sandbox/test_resolve_workspace.py` — solitary-unit на реальной ФС (`tmp_path`)
2. **Тестирует**: `executor.sandbox :: resolve_workspace`
3. **Суть**: Суита проверяет единственную проверку, которую executor вообще делает над запросом: `project_id` — это один безопасный сегмент пути, а канонизированный результат обязан остаться внутри корня workspace'ов. Она страхует от того, чтобы тупой исполнитель **усиливал** плохой запрос — traversal-строкой или симлинком, уводящим за корень, — и фиксирует, что отсутствующий workspace остаётся ошибкой: executor не создаёт директорий, потому что владельцем каталога на общем volume обязан быть backend (под gVisor запись требует совпадения uid).
4. **Кейсы**: существующий проект резолвится в свою директорию; безопасные сегменты принимаются (буквы, дефис, подчёркивание, точка, регистр, 128 символов — parametrize); отклоняются пустая строка, `.`, `..`, `../etc`, `../../etc/passwd`, `a/b`, `/absolute`, `p1/../p2`, `..%2fetc`, пробел, `;`, `$`, 129 символов (parametrize); симлинк, уводящий за корень, отклоняется после канонизации; симлинк внутри корня принимается; отсутствующая директория → `WorkspaceMissingError`, и директория не создана; файл вместо директории → `WorkspaceMissingError`.

### `test_run_job.py` — исполнение под deadline

1. **Файл**: `tests/runner/test_run_job.py` — integration на реальных процессах ОС, без дублей (джоба запускается без bwrap)
2. **Тестирует**: `executor.runner :: run_job`
3. **Суть**: Суита проверяет то, что нельзя проверить на структуре данных: deadline действительно срабатывает, группа процессов умирает вместе с внуками, а пайпы вычитываются, а не буферизуются. Она страхует главный продуктовый инвариант — исход джобы всегда возвращается результатом, а не исключением: агент читает stderr упавшей или убитой джобы и чинит код, тогда как исключение прочиталось бы как отказ инфраструктуры. Обратная сторона той же границы закреплена отдельно: невозможность **запустить** джобу (нет `bwrap`/`unshare`) — это как раз исключение и единственный ERROR-лог сервиса, и он обязан нести трейсбек (`exc_info`), потому что других данных об этом отказе нигде нет. Потолок вывода проверяется вместе с тем, что джоба при этом штатно завершается, а не виснет на заполненном пайпе до дедлайна; продолжение той же линии — дренаж с дедлайном: процесс, переживший джобу с унаследованным пайпом, стоит куска вывода, но не ответа. Набор env джобы зажат с двух сторон: сверху — инвариант изоляции, снизу — сторож дрейфа между `runner._job_env()` и `--setenv` в `sandbox.py` (два независимых источника одного и того же списка).
4. **Кейсы**: успешная команда → stdout, `exit_code=0`, `timed_out=False`; упавшая → код возврата и stderr доехали; `cwd` = workspace (относительная запись легла в него); env джобы собран с нуля — переменные сервиса и `DATABASE_URL` не видны, и все пять ожидаемых переменных на месте; выход за deadline → `timed_out=True`, отрицательный `exit_code`, диагностика в stderr, возврат в пределах дедлайна с запасом; внуки джобы после дедлайна перестают писать в файл (kill добивает потомков); вывод сверх потолка усечён с пометкой на каждом потоке отдельно (parametrize stdout/stderr) при `exit_code=0` и без таймаута; вывод в пределах потолка возвращается дословно; фоновый процесс, переживший джобу и держащий пайп, → возврат по `kill_grace_seconds` (не по дедлайну), прочитанный хвост на месте, маркер `output capture incomplete` в stderr и `output_incomplete=True` в WARNING-логе; недекодируемые байты → replacement-символы, без исключения; незапускаемая команда → `OSError` наружу плюс единственный ERROR-лог `job launch failed` с `exc_info`; исход логируется одной строкой `job finished` — WARNING при таймауте, INFO при успехе, с `project_id`/`exit_code`/флагами усечения.

### `test_jobs.py` — HTTP-контракт `POST /jobs`

1. **Файл**: `tests/api/test_jobs.py` — integration, ASGI-клиент (`httpx.AsyncClient` + `ASGITransport`) поверх реального `create_app()`
2. **Тестирует**: `executor.api.routes :: create_job`, `executor.api.schemas :: JobRequest/JobResponse`, барьерные handler'ы `executor.main`
3. **Суть**: Суита фиксирует контракт, под который T1 пишет tool-обвязку: один эндпоинт, тело с `project_id` и ровно одним из `cmd`/`code`, ответ ровно из трёх полей. Главное, что она разделяет, — чья это ошибка: упавшая или вышедшая за deadline джоба возвращается как 200 с диагностикой (агент прочитает и починит код), а кривой запрос или неизвестный проект — как 4xx, и никогда как 500 из непойманного доменного исключения. Отдельно закреплён защитный потолок таймаута с обеих сторон: сверху — кламп до `max_timeout_seconds`, снизу — отрицательный ввод в ноль; обе границы пишут WARNING, иначе неверно настроенный backend-deadline выглядел бы просто флаком, а джоба, убитая мгновенно, — сломанным executor'ом. Таблица небезопасных `project_id` здесь не повторяется: какие строки считаются небезопасными, решает и исчерпывающе проверяет `test_resolve_workspace.py`, а на HTTP-слое проверяется единственный путь «доменное исключение → барьер → 400» — хватает двух значений.
4. **Кейсы**: `cmd` исполняется, ответ — ровно `{stdout, stderr, exit_code}`; `cmd` идёт через шелл (пайпы и `&&` работают); PATH джобы остаётся собранным сервисом, а не унаследованным/перестроенным логин-шеллом; ненулевой exit → 200 с кодом и stderr; таймаут → 200 с диагностикой в stderr; таймаут выше потолка клампится и пишет WARNING с обоими значениями; отрицательный таймаут клампится в `0.0` с тем же WARNING, джоба убивается сразу и говорит об этом в stderr; таймаут в пределах потолка WARNING не пишет; отсутствующий `timeout` берёт дефолт сервиса и тоже применяется; ветка `code` исполняет исходник и отдаёт трейсбек падения; временный файл ветки `code` создаётся именно в наблюдаемой директории (джоба печатает свой `__file__` — иначе кейс об удалении вакуумен: перестань хендлер уважать `tempfile.tempdir`, и тест смотрел бы на заведомо пустой каталог), после прогона удалён и в workspace не появился; тело без `cmd`/`code`, с обоими сразу и без `project_id` → 422 (parametrize); небезопасный `project_id` → 400 (parametrize из двух значений); неизвестный проект → 404, директория не создана.

### `test_logging.py` — формат и уровень логов

1. **Файл**: `tests/observability/test_logging.py` — solitary-unit, шов — перехват stdout (`capsys`)
2. **Тестирует**: `executor.logging :: configure_logging`
3. **Суть**: Суита проверяет, что оператору вообще есть что читать: JSON-строка на событие, фильтрация по заданному уровню и отрендеренный трейсбек вместо голого флага. Последний кейс — закрывающий для прод-фикса T3.5 (`format_exc_info` в цепочке процессоров): без него единственный ERROR-лог сервиса сообщал бы «что-то упало» ровно в той ситуации, где больше никаких данных нет. Опечатка в `EXECUTOR_LOG_LEVEL` роняет старт, а не молча оставляет прежний уровень.
4. **Кейсы**: событие выходит одной JSON-строкой с уровнем и timestamp; уровень ниже настроенного отфильтрован; `exc_info=True` рендерится в поле `exception` с трейсбеком (и поле `exc_info` в выводе не остаётся); неизвестный уровень → отказ конфигурации.

### `test_app_boot.py` — сборка приложения

1. **Файл**: `tests/smoke/test_app_boot.py` — smoke, ASGI-клиент
2. **Тестирует**: `executor.main :: create_app`
3. **Суть**: Дешёвая проверка, что приложение собирается и обе точки на месте: `/jobs` для backend и `/health` для healthcheck'а compose. Ни lifespan, ни соединений у сервиса нет, поэтому на этом уровне проверять больше нечего.
4. **Кейсы**: `create_app()` регистрирует `/health` и `/jobs`; `GET /health` → 200 `{"status": "ok"}`.

**Осознанно не покрываем автотестом:**

- **Фактическая изоляция под bwrap** (чужой workspace = ENOENT, `/skills` = EROFS, пустой netns, коллапс pid-namespace) — требует непривилегированных user namespaces, недоступных в агентской и CI-песочнице, а errno сетевого отказа отличается между реальным ядром и gVisor → смоук образа `smoke/smoke_sandbox.py` (`make smoke-executor`), ручные `{T3.3}`, `{T3.5}` и cross-cutting B2/B3/B6b/B6c/B7.
- **Состав толстого образа** (numpy/pandas/matplotlib, pandoc, python-docx + docxcompose, pypdf, шрифты с кириллицей) — проверяется только внутри собранного образа, в venv репозитория этот набор ничего не доказывает → `make smoke-executor`, ручной `{T3.2}` (B4).
- **Свойства образа**: non-root uid 10001, отсутствие dev-группы (`pytest`), наличие `bwrap`/`unshare`/`pandoc` → ручные `{T3.1}`, `{T3.6}` (B5).
- **Ветка `code` под песочницей** (ro-bind исходника на `/tmp/job.py`, интерпретатор из venv образа, читаемый трейсбек) — автотест закрывает порядок argv и поведение ветки на dev-пути, остальное живёт в образе → `{T3.8}`.
- **Три звена kill-контракта вместе** — автотест на голом процессе проверяет только первое звено (`killpg` по группе обёртки); `--die-with-parent` и коллапс pid-ns наблюдаемы лишь под настоящим bwrap → `{T3.7}`, B8.
- **Compose-топология**: сеть `exec` с `internal: true`, `runtime: runsc`, потолки `cpus`/`mem_limit`/`pids_limit`, `stop_grace_period` ≥ deadline, единый uid app = executor = джоба — файлы чужого трека (T1), проверяются только на живой топологии → cross-cutting Layer 2 (B1, B2, B3, B5, B6c, B8, B9).
- **Транспортные отказы** (executor недоступен: connect refused, HTTP-таймаут) — это поведение tool-обвязки backend, а не executor'а → тестовый скоуп T1.
- **Параллельные джобы и размер threadpool** — контракта per-job на этот счёт нет (потолки стоят на контейнере целиком, голодание принято брифом), автотест зафиксировал бы деталь реализации → не покрываем осознанно.
- **Сами смоук-скрипты** (`services/executor/smoke/`) — это тестовый инструмент, а не прод-код; их корректность проверяется негативной пробой ворот `{T3.4}`.

**Замеченные прод-баги (для fixer'а, сам не чиню):** не найдено — все проверенные контракты
(валидация `JobRequest`, кламп с WARNING, барьерные 400/404, резолв workspace, фиксированные
поля `JobResponse`, потолок вывода с пометкой, таймаут как результат, scrubbed env,
`sandbox_enabled=False` → WARNING) реализованы так, как их описывают бриф и план.

Одно наблюдение **не в статусе бага**, на усмотрение ревьюера: в `runner._kill_process_group`
ветка `ProcessLookupError` возвращает управление, не вызвав `proc.wait()`, — тогда
`JobResult.exit_code` был бы `None` и ответ упал бы на валидации `JobResponse`. Практически
недостижимо (собственный незажатый потомок остаётся зомби до `wait`, и `os.getpgid` на зомби
работает), автотеста поэтому нет; фиксирую как известную теоретическую щель, а не как дефект.
Ревьюер согласился с оценкой (R10), fixer добавил `proc.wait()` как hardening — кейса
по-прежнему нет и не будет: путь недостижим, мутацией не закрывается.

### Layer 0: Automated gate

- [x] `make check` — ruff + mypy (backend, siem-service, **executor**, tools) + import-linter + arch-checker → **0 ошибок**. Полный репозиторный прогон зелёный целиком: `ruff check` — clean, `ruff format --check` — 370 файлов, mypy backend 274 / siem-service 43 / **executor 32** / tools 8 — все `Success: no issues found`, import-linter 9/9 KEPT. `arch_checker` — 9 WARN, все унаследованные size-чеки в `backend/**` (`main.py` 821 строка, `app/agent` 14 модулей и т.п.), ни одного по executor'у; AST-проверки passed. Ожидавшегося красного mypy по `backend/tests/chat/**` (незавершённая работа T1 в этом же worktree) на момент прогона нет — гейт чист без исключений.
- [x] executor-строка `make test`: `uv run --package executor pytest -c services/executor/pyproject.toml --rootdir services/executor services/executor/tests` → **87 passed in 6.33s**. Раскладка сошлась с § Дизайн автотестов: api 18, config 11, observability 4, runner 14, sandbox 14 + 24, smoke 2. `asyncio: mode=Mode.AUTO` подтверждён шапкой прогона (закрытие R5 фактически применено).
- [x] `make test-parallel` (тот же набор под `-n auto`) — зелёный: **87 passed in 5.62s**, 12 воркеров, `created: 12/12 workers`. Порядконезависимость и отсутствие общего состояния подтверждены на этом хосте.

---

## Ручные кейсы + статусы

### Layer 1: Трек T3 — executor-сервис (нужен только собранный образ, compose не нужен)

- [x] `{T3.1}` `make docker-build-executor` → сборка проходит (образ `learnflow-executor:local`, sha256:749d5eac7df7); `docker run --rm learnflow-executor:local id` → `uid=10001(executor) gid=10001(executor) groups=10001(executor)` — единый uid межтрекового контракта 4 на месте. *(Образ пересобирался трижды по ходу `{T3.4}`; финальное состояние — сборка с откаченной правкой, на ней прогнан итоговый зелёный смоук.)*
- [x] `{T3.2}` `make smoke-executor` (дефолтный `RUNTIME=runc`) → `PASS matplotlib_png`, `PASS pandoc_docx`, `PASS pdf_text`, `PASS python_docx`, `PASS fonts`, `PASS sandbox`, `run_all: all 6 scenarios passed`, exit 0. Тулчейн внутри образа: numpy 2.5.2, pandas 3.0.5, matplotlib 3.11.1, pandoc 2.17.1.1 — B4 закрыт на уровне образа. runs: r1 ✅ → r2 ❌ (намеренная порча в `{T3.4}`) → r3 ✅ (после отката) → r4 ✅ (перепрогон после фикса R11 в Dockerfile — все шесть сценариев зелёные, `tini` как ENTRYPOINT смоук-пути не задел).
- [x] `{T3.3}` 🔴 сценарий `smoke_sandbox.py` внутри того же прогона → `PASS`. Для протокола прогнан отдельно с печатью самих проверок (тот же `run_job` + тот же `_INNER_SCRIPT` внутри образа): `SMOKE_SANDBOX foreign_enoent=True no_network=True own_workspace=True skills_erofs=True`, `EXIT 0 TIMED_OUT False`, `duration_ms=115`. То есть запись+чтение своего `/workspace` — успех, `/workspaces/other-project/secret.txt` — `FileNotFoundError` (точки монтирования `/workspaces` в mount-ns джобы нет вовсе), запись в `/skills` — `OSError` (EROFS), `connect(1.1.1.1:443)` — `OSError` (сеть недостижима). B6b/B6c/B7/B3 на уровне образа под runc закрыты.
- [x] `{T3.4}` негативная проверка ворот прогнана в **двух** режимах отказа, оба поймала. (а) Недостающая транзитивная зависимость — `import pypdf` → `import pypdf_missing_transitive_dep`, пересборка образа: `ModuleNotFoundError` с путём `/app/services/executor/smoke/smoke_pdf_text.py`, `run_all: 1/6 scenario(s) failed`, `make: *** Error 1` (exit 2). (б) Отказ внутри `main()` — испорчен `_MARKER`: `FAIL pdf_text: marker 'SMOKE_PDF_MARKER_BROKEN_T3_4_PROBE' not found in extracted text: 'SMOKE_PDF_MARKER'` в stderr + традиционный трейсбек, `run_all: 1/6 scenario(s) failed`, ненулевой код. Нюанс: одно-строчный контракт `FAIL <name>: <reason>` из `_common.report` работает только на отказе внутри `main()`; при отказе на импорте `report()` не успевает выполниться, и сценарий называется путём файла в трейсбеке — диагностично, но формат другой. Обе правки откачены, `git status`/`grep` подтверждают исходное содержимое (`import pypdf`, `_MARKER = "SMOKE_PDF_MARKER"`), пересборка + перепрогон → снова `all 6 scenarios passed`, exit 0.
- [ ] ⚠️ `{T3.5}` 👤 **deferred — заблокировано окружением.** Прод-половина (`make smoke-executor RUNTIME=runsc` на VM с установленным runsc → зелёный sandbox-сценарий) не прогонялась: на этом dev-хосте runsc не зарегистрирован в демоне — `docker info` даёт `Runtimes: io.containerd.runc.v2 runc`, `Default Runtime: runc`. Остаётся шагом чек-листа деплоя для архитектора. Dev-половина кейса прогнана и **зелёная**: `make smoke-executor RUNTIME=runsc` падает внятно — `docker: Error response from daemon: unknown or invalid runtime name: runsc`, `make: *** Error 125`, тихого фолбэка на runc нет (параметр реально доезжает до `docker run`). Без runsc bwrap-слой всё равно проверен под runc в `{T3.2}`/`{T3.3}`; непроверенным остаётся ровно поведение errno сети под gVisor netstack (`EAFNOSUPPORT` вместо `ENETUNREACH`, см. § Решения summary) — на факт изоляции не влияет.
- [x] `{T3.6}` `docker run --rm learnflow-executor:local sh -c 'pip list 2>/dev/null | grep -c pytest'` → `0` — dev-группа в образ не просочилась. Тулчейн на месте: `bubblewrap 0.8.0`, `unshare from util-linux 2.38.1`, `pandoc 2.17.1.1` (версии bookworm-slim; на dev-хосте bwrap 0.11 — разница базы, не дефект). Дополнительно проверен импорт всего джобового набора внутри образа: numpy 2.5.2 / pandas 3.0.5 / matplotlib 3.11.1 / python-docx / pypdf импортируются.
- [x] `{T3.7}` 🔴 kill-цепочка под настоящим bwrap: контейнер образа (runc + три `security-opt` флага смоука), `POST /jobs {"project_id":"p1","cmd":"sleep 300 & sleep 300","timeout":2}` → HTTP 200 за **2.11 с** wall-clock, тело `{"stdout":"","stderr":"\n[executor] job exceeded timeout of 2.0s — killed (SIGTERM, then SIGKILL after 5s grace)","exit_code":-15}`, JSON-лог `job finished` уровня warning с `duration_ms=2003, timed_out=true`. Процессов `sleep` после возврата не осталось ни одного — ни внутри контейнера (`procps` в образе нет, эквивалент `ps -eo pid,comm` снят обходом `/proc`: только `1 uvicorn`, `28 bwrap`, `38 python`), ни на хосте. Коллапс pid-namespace добил обоих внуков — заявленный кейсом инвариант выполнен. **⚠️ Находка вне ассерта кейса (передана оркестратору, не чинилась):** каждая джоба оставляет одного зомби `bwrap` с `PPid: 1` — `State: Z (zombie)`, `Uid: 10001`. Накопление детерминированное и не зависит от исхода джобы: 4 таймаута → 4 зомби, +3 успешных `echo ok` → 7, после `{T3.8}`/`{T3.9}` → 9 зомби на 9 джоб, ровно 1:1. Причина: bwrap-потомок переживает свою обёртку и реперентится на PID 1 контейнера, а PID 1 здесь — `uvicorn` (в `services/executor/Dockerfile` нет ни `tini`, ни entrypoint-скрипта, ни `init`), и сирот он не жнёт. Под `pids_limit` из прод-топологии (design-brief § Executor, файл T1) это медленная утечка PID-слотов: контейнер деградирует до невозможности форкать после N джоб, а перезапуск маскирует симптом. Кандидат-фикс лежит в двух чужих для этого кейса местах: `init: true` в compose-блоке executor'а (T1) либо `tini` как ENTRYPOINT образа (T3.6). — **Находка заведена как R11 и закрыта fixer'ом** (`tini` в образ). runs: r1 ✅ (kill-контракт зелёный, попутно вскрыт зомби-лик) → r2 ✅ (после фикса R11: шесть джоб, ноль зомби, PID 1 — `tini`).
- [x] `{T3.8}` ветка `code` под песочницей: `POST /jobs {"project_id":"p1","code":"import numpy; print(numpy.__version__); raise ValueError('x')"}` → HTTP 200, `stdout="2.5.2\n"` (та же версия, что `uv sync` положил в `[project.dependencies]` — интерпретатор джобы действительно venv образа `/app/.venv`, не системный python базового образа), `exit_code=1`, трейсбек в stderr начинается с `File "/tmp/job.py", line 1, in <module>` — фиксированный ro-bind-путь на месте, читаемость трейсбека для агента обеспечена. Закрытие находки T3.5 про резолв интерпретатора подтверждено на боевом HTTP-пути, а не только прямым прогоном argv.
- [x] `{T3.9}` 📊 джоба не видит env сервиса на боевом пути: контейнер поднят с посторонними `SECRET_SENTINEL=leaked-value` и `DATABASE_URL=postgresql://fake/db` (наличие обеих в окружении сервиса подтверждено `docker exec … env`), затем `POST /jobs {"cmd":"env | sort"}` → в выводе джобы ровно `HOME=/workspace`, `LANG=C.UTF-8`, `MPLCONFIGDIR=/tmp/mpl`, `PATH=/app/.venv/bin:/usr/local/bin:/usr/bin:/bin`, `XDG_CACHE_HOME=/tmp/cache` плюс `PWD`/`SHLVL`/`_`, которые ставит сам `bash` уже внутри песочницы (не унаследованы). Ни `SECRET_SENTINEL`, ни `DATABASE_URL` не доехали — B1 подтверждён на уровне процесса под реальным `--clearenv`.

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [ ] `B1` `docker exec` в контейнер executor'а → в env нет `DATABASE_URL`, `JWT_SECRET`, LLM-ключей (секреты основного стека до сервиса не доезжают by design).
- [ ] `B2` 🔴 из джобы коннект к `db:5432` и `redis:6379` → отказ: ни DNS, ни маршрута (executor вне стековой сети).
- [ ] `B3` 🔴 из джобы `curl https://example.com`, `pip install requests`, коннект к `app:8000` → отказ (`internal: true` без NAT плюс пустой netns джобы).
- [ ] `B5` `docker inspect` контейнера executor'а → `Runtime: runsc`, процесс внутри — non-root (uid 10001), порт наружу не опубликован.
- [ ] `B6c` 🔴 джоба пишет в свой workspace на общем volume, каталог которого создал backend → успех. Расхождение uid между app и executor вскрывается здесь и только здесь (`EINVAL` под gVisor даже при mode 777).
- [ ] `B8` бесконечный цикл, запрошенный агентом через `execute_code` → джоба убита по deadline вместе с потомками, диагностика доехала до агента, чат живой; fork-bomb упирается в `pids_limit` контейнера, а не кладёт хост.
- [ ] `B9` «Стоп» пользователя во время долгой джобы → ход остановлен, следующее сообщение работает; файлы-сироты от дожившей джобы допустимы (отмена v1).
- [ ] 📊 `stop_grace_period` executor-контейнера ≥ deadline: `docker compose stop executor` во время идущей джобы → in-flight джоба доживает и дописывает файл, SIGKILL не рубит запись на полпути.
- [ ] 📊 backend-deadline ≤ `EXECUTOR_MAX_TIMEOUT_SECONDS`: на нормальном ходе агента в JSON-логах executor'а **нет** события `timeout clamped` (кламп — защитный потолок, а не рабочий режим).
- [ ] 📊 в Langfuse-спане tool-вызова джобы присутствуют `exit_code` и длительность (§ Конвенции брифа; наблюдаемость рендер-скиллов).

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] `A1` 👤 «Посчитай статистику по этому CSV» → агент пишет Python, исполняет через executor, отвечает числами; лента показывает вызов и результат.
- [ ] `A2` 👤 «Какая версия pandoc в окружении?» → ответ из stdout джобы (`run_command` доезжает до образа с запечённым тулчейном).
- [ ] `A10` 👤 джоба падает из-за ошибки в коде → агент читает stderr, чинит и доводит до результата; thread живой (ошибка джобы — рабочий цикл, не отказ).
- [ ] `A12` 👤 прикреплённый PDF → агент сам извлекает текст джобой (pandoc/pypdf в образе) и работает с содержимым: ingestion и есть runtime.

---

## Находки ревью [severity+owner]

> Пишет **test-reviewer** (adversarial-ревью тестов против контракта, read-only). Каждая находка —
> severity (**blocker** / **major** / **minor**) + владелец фикса: `[test]` (test-author) /
> `[prod]` (fixer) / `[infra]` (`packages/testing`) / `[doc]`. На фазе GREEN fixer чинит `[prod]`,
> test-author — `[test]`; закрытую/эскалированную находку помечают здесь же. Чисто — секция пустая.

**Прогоны ревьюера (read-only, 2026-08-11):** executor-строка `make test` → **88 passed, 5.3 s**;
`-n auto` трижды подряд → 88 passed (порядконезависимость и отсутствие общего состояния
подтверждены); `tests/runner` + `tests/api` трижды под искусственной CPU-загрузкой (busy-loop на
каждое ядро) → 33 passed, ~6 s — тайминги субпроцессных кейсов запас держат;
`ruff check` / `ruff format --check` / `mypy services/executor/` → чисто.

R1 **major** `[prod]` `services/executor/executor/runner.py:175` — единственный ERROR-лог сервиса (`job launch failed`) пишется без `exc_info=True`, поэтому добавленный в T3.5 `format_exc_info` (`executor/logging.py:28`) на боевом call-site не даёт ничего: в JSON едут только `error`/`error_type`, трейсбека нет. Конвенция требует `exc_info=True` при логировании исключений (`doc/tech/conventions.md:547`), а `summary.md:480-487` и § `test_logging.py` выше считают находку закрытой — закрыта половина (процессор добавлен, аргумент на месте вызова не появился). → fixer: `logger.error("job launch failed", …, exc_info=True)`; test-author: доассертить это на боевом кейсе `tests/runner/test_run_job.py:206-210` (`capture_logs` отдаёт событие до процессоров → `entry["exc_info"] is True`), рендер трейсбека уже сторожит `tests/observability/test_logging.py:53`; поправить формулировку закрытия в `summary.md`. — **Закрыто (GREEN, attempt 1):** `exc_info=True` добавлен на боевом call-site; поле `"exception"` с полным трейсбеком проверено эмпирически на реальной цепочке процессоров, формулировка закрытия в `summary.md` поправлена (в T3.5 была закрыта только процессорная половина). Доассерт на кейсе — за test-author'ом. — **Доассерт сдан (GREEN, attempt 1):** `tests/runner/test_run_job.py` на боевом кейсе `job launch failed` ассертит `entry["exc_info"] is True`; мутация (снять аргумент на call-site) красит ровно этот кейс.

R2 **minor** `[test]` `tests/sandbox/test_build_job_argv.py:67-79` — три флага kill-контракта проверяются как `flag in argv`, без позиции, хотя позиция контрактна: флаг обязан стоять в сегменте `bwrap … --`. Перенос любого из них за `--` (флаг молча уезжает в argv джобы, изоляция теряется) кейс не покрасит. То же слабое место у `--clearenv` (`:159`). → ассертить по срезу `argv[argv.index("bwrap") + 1 : argv.index("--")]`. — **Закрыто (GREEN, attempt 1):** введён хелпер `_bwrap_flags(argv)` на этом срезе, через него проверяются три флага kill-контракта (parametrize) и `--clearenv`. Мутация (перенос `--new-session` за `--`) красит нужный параметр — до правки тот же перенос кейс не ловил.

R3 **minor** `[test]` `tests/api/test_jobs.py:199-218` — «временных файлов не осталось» проходит вакуумно: если `monkeypatch.setattr(tempfile, "tempdir", …)` перестанет влиять (переход прода на `NamedTemporaryFile(dir=…)`/`TemporaryDirectory`), файл уедет в системный `/tmp`, `scratch` окажется пуст и кейс останется зелёным, ничего не проверив. → сначала доказать шов (`code` печатает `__file__`, assert на префикс `scratch`), потом ассертить удаление. — **Закрыто (GREEN, attempt 1):** джоба печатает `__file__`, кейс ассертит префикс `scratch/`, и только потом — пустой `scratch` и чистый workspace. Мутация (`mkstemp(..., dir="/tmp")`, шов перестаёт действовать) красит кейс.

R4 **minor** `[test]` `tests/runner/test_run_job.py:83-92` — env джобы ограничен только сверху (`set(job_env) <= {…}`): выпадение любой из пяти переменных из `runner._job_env()` (`runner.py:52-59`) кейс не покрасит. А это второй, ни с чем не сверяемый источник того же набора (первый — `--setenv` в `sandbox.py`, там ассерт точный) — дрейф между ними сейчас без сторожа. → добавить нижнюю границу: `{"PATH","HOME","LANG","MPLCONFIGDIR","XDG_CACHE_HOME"} <= set(job_env)`. — **Закрыто (GREEN, attempt 1):** нижняя граница добавлена (записана как `set(job_env) >= EXPECTED_JOB_ENV_KEYS` — форма из находки ловится ruff SIM300), константа названа так же, как в `test_build_job_argv.py`. Мутация (убрать `MPLCONFIGDIR` из `runner._job_env()`) красит кейс.

R5 **minor** `[test]` `services/executor/pyproject.toml:23-30` — нет `asyncio_mode = "auto"` (есть в `backend/pyproject.toml:38` и `services/siem-service/pyproject.toml:25`; `conventions/testing.md` § Async называет auto движком проекта), поэтому все async-кейсы держатся на ручном `@pytest.mark.asyncio`. False-green проверен эмпирически и **не подтверждён**: под pytest 9 + pytest-asyncio 1.4 незамаркированный `async def`-тест падает громко («async def functions are not natively supported»), а не скипается — расхождение чисто конвенционное. Там же описание маркера `integration: requires real Postgres (testcontainers)` скопировано из siem-service и для executor'а неверно (БД нет; integration здесь = реальные процессы ОС). → добавить `asyncio_mode`/`asyncio_default_fixture_loop_scope`, переписать описание маркера. — **Закрыто (GREEN, attempt 1):** обе опции добавлены дословно как в backend/siem-service, описание маркера переписано под executor (`integration: spawns real OS processes (the executor owns no database)`); 13 ручных `@pytest.mark.asyncio` сняты — в auto-режиме они шум, и в backend/siem их нет.

R6 **minor** `[test]` `tests/api/test_jobs.py:245` — parametrize из пяти небезопасных `project_id` дублирует таблицу из 13 значений в `tests/sandbox/test_resolve_workspace.py:48-70`; на HTTP-слое проверяется ровно один путь (доменное исключение → барьерный handler → 400), и для него хватает одного-двух значений. → сжать до `"../etc"` (+ опционально `""`). — **Закрыто (GREEN, attempt 1):** parametrize сжат до `["../etc", ""]` (−3 кейса), в докстринге названо, где живёт полная таблица.

R7 **minor** `[test]` `tests/conftest.py:49-66` — `_reset_structlog` лезет во внутренности ленивого прокси structlog (`module.logger.__dict__.pop("bind")`). При смене реализации кэша в structlog захват молча перестанет работать, и негативные лог-ассерты (`test_build_job_argv_sandboxed_does_not_warn:227`, `test_post_jobs_timeout_within_ceiling_is_not_warned:146`) станут вакуумно зелёными; позитивные кейсы в тех же суитах при этом покраснеют, так что вектор ограничен и находка минорная. → либо гасить кэш публичным API после `create_app()` (`structlog.configure(cache_logger_on_first_use=False)`), либо оставить как есть, привязав докстринг к версии structlog. — **Закрыто (GREEN, attempt 1):** выбран третий вариант, тоже на публичном API и без привязки к версии — `_reset_structlog` выдаёт модулям свежие прокси (`module.logger = structlog.get_logger()`) вместо чистки кэша: неиспользованный прокси ничего не закэшировал по определению. Непустота отрицательных лог-ассертов подтверждена мутацией: WARNING на сандбоксированной ветке и безусловный `timeout clamped` красят ровно `test_build_job_argv_sandboxed_does_not_warn` и `test_post_jobs_timeout_within_ceiling_is_not_warned`.

R8 **minor** `[test]` `tests/api/test_jobs.py:110-146` — кламп `timeout` покрыт только сверху; нижняя граница `max(timeout, 0.0)` (`api/routes.py:50`) не проверена, хотя исход заметный: `timeout: -1` → 0.0 + WARNING → джоба убивается мгновенно. Deadline — критпуть, § Coverage требует на нём edge/negative. → добавить кейс с отрицательным `timeout`. — **Закрыто (GREEN, attempt 1):** `test_post_jobs_negative_timeout_is_clamped_to_zero_and_warned` — `timeout: -1` → 200, WARNING `timeout clamped` с `requested_timeout=-1`/`clamped_timeout=0.0`, диагностика «exceeded timeout of 0.0» в stderr.

R9 **minor** `[prod]` `services/executor/executor/runner.py:206-207` — `stdout_thread.join()` без таймаута безопасен только под песочницей (коллапс pid-ns закрывает унаследованные концы пайпов). На dev-пути `sandbox_enabled=False` — ровно том, на котором гоняется весь автонабор, — отцепившийся внук (`setsid … &`) держит пайп открытым, и `run_job` висит сверх deadline, не отдавая ответ. Автотеста на это нет и заводить не следует (кейс сам зависнет). → `join(timeout=…)` с отбросом хвоста либо явная строка об ограничении dev-hatch в докстринге `runner.py`. — **Закрыто (GREEN, attempt 1):** ожидание ридеров ограничено (`_drain()`, общий дедлайн `kill_grace_seconds`) — джоба отдаёт результат с прочитанным хвостом, деградация видна маркером в `stderr`, полем `output_incomplete` в логе и уровнем WARNING; выбран фикс, а не докстринг: документация не убирает бесконечно висящий запрос. — **Автотест добавлен (GREEN, attempt 1, test-author):** деградация автоматизируема без риска зависания — сам фикс делает ожидание конечным. `test_run_job_reports_degraded_capture_when_a_process_outlives_the_job`: `bash -c "echo captured; sleep 10 & exit 0"` при `sandbox_enabled=False` и дедлайне 30 с — возврат за ~1 с (по `kill_grace_seconds`, не по дедлайну), прочитанный хвост на месте, маркер в stderr и `output_incomplete=True` в WARNING-логе. Мутация (снять дописывание маркера) красит кейс.

R10 **minor** `[prod]` `services/executor/executor/runner.py:128-129` — оценка наблюдения автора тестов: ветка `ProcessLookupError` возвращает управление без `proc.wait()` → `proc.returncode is None` → `JobResult.exit_code=None` → 500 на валидации `JobResponse`. Согласен с автором — недостижимо: незажатый прямой потомок остаётся зомби, а `getpgid`/`killpg` на зомби отрабатывают штатно, так что ESRCH здесь не возникает; кейса не нужно, мутацией не закрывается. → одна строка `proc.wait()` перед `return` как hardening, на усмотрение fixer'а. — **Закрыто (GREEN, attempt 1):** `proc.wait()` перед `return` в ветке `ProcessLookupError` — одна строка hardening'а; недостижимость подтверждена, но `exit_code=None` в контракте не остаётся.

R11 **major** `[prod]` `services/executor/Dockerfile:84` — находка не ревьюера, а тестировщика: вскрыта ручным прогоном `{T3.7}` (наблюдение за таблицей процессов, вне ассерта самого кейса), заведена сюда, чтобы у прод-бага был один реестр. Каждая джоба оставляет зомби-процесс `bwrap` (`State: Z`, `PPid: 1`, `Uid: 10001`); накопление 1:1 с числом джоб и не зависит от исхода (9 джоб → 9 зомби). Причина: bwrap-потомок переживает свою обёртку и реперентится на PID 1 контейнера, а PID 1 — `uvicorn` из `CMD` (ни `tini`, ни entrypoint-скрипта в образе нет), сирот он не жнёт. Под `pids_limit: 256` прод-топологии это медленная утечка PID-слотов до отказа контейнера форкать; рестарт маскирует симптом. Автотестом не ловится в принципе — зомби живёт в pid-namespace контейнера, а не в процессе сервиса. → fixer: init-процесс в образ. — **Закрыто (GREEN, attempt 1):** решением архитектора выбран `tini` в образе (`ENTRYPOINT ["tini", "--"]` + пакет `tini` в apt-слое), а не `init: true` в compose — гарантия должна держаться везде, где запускается образ, а не только там, где не забыли флаг. Верифицировано по первопричине на пересобранном образе: шесть джоб (три успешных, два таймаута, одна `code` с трейсбеком) → в таблице процессов ноль записей со `State: Z`, `PID 1` — `tini`, `uvicorn` его прямой потомок; до фикса тот же прогон на четырёх джобах давал ровно четыре зомби `bwrap` с `PPid: 1`. Kill-контракт не задет: `docker stop` — graceful shutdown uvicorn за 0.84 с, exit 143 (tini пробрасывает SIGTERM), смоук зелёный целиком.

**Чисто:** false-green и тавтологий сверх R3 не найдено — ассерты содержательны, дублей нет вообще (чистые функции и реальные процессы), проверок вызовов вместо результата нет. Флак не воспроизведён: 3× `-n auto` и 3× субпроцессные суиты под полной CPU-загрузкой зелёные; тайминговые кейсы устроены устойчиво (`run_job` возвращается только после EOF на пайпах, то есть после смерти внуков, поэтому окна `sleep 0.3/0.5` в кейсе про внуков — не гонка, а самопроверка `heartbeat.exists()`, дающая при промахе внятный fail, а не зелёный). Инфра по слою корректна: Postgres/testcontainers не тянутся, `packages/testing` осознанно не переиспользуется (там Postgres/LLM/SSE — у executor'а ничего из этого нет), шов api-суиты честный (`app.dependency_overrides` на `get_settings` с реальным `Settings`, не магические значения). Контракты сверены с брифом, не только с планом: префикс `unshare -U --map-current-user -n` и отсутствие `--unshare-net`, три флага kill-контракта, mount-набор, `--clearenv` + пять `--setenv`, `extra_ro_binds` после `--tmpfs /tmp`, фиксированные поля `JobResponse`, дефолты восьми knobs — совпадают с § Executor / § Конвенции / § Безопасность брифа и таблицей knobs плана; жёсткая привязка порядка флагов внутри `unshare`-префикса (`argv[:5]`) прибита к формулировке брифа осознанно и находкой не считается. Ветка `code` (temp-файл вне workspace + ro-bind на `/tmp/job.py`) сверена с резолюцией OQ-1 — расхождения с брифом нет. Нейминг `test_<unit>_<condition>_<expected>`, AAA и раскладка по подсистемам выдержаны; заявленные счётчики (88 кейсов, 24 в resolve, 11 в settings) сходятся с фактическим прогоном. Целостность (A6): тест-файлы прод-код не трогают, авторы разведены по фазам согласно `summary.md` — по git это подтвердить нельзя, весь `services/executor/` untracked одним куском.

---

## Покрытие

| Контракт / риск (бриф, план, acceptance) | Закрывающие кейсы |
|---|---|
| `POST /jobs` — фиксированные поля ответа (межтрековый контракт 2) | `test_jobs.py` (ответ ровно `{stdout, stderr, exit_code}`) |
| Ровно одно из `code`/`cmd` | `test_jobs.py` (422 на оба/ни одного) |
| Кламп `timeout` + WARNING (сверху и снизу); дефолт при `None` | `test_jobs.py` (четыре кейса), Layer 2 (`timeout clamped` отсутствует на нормальном ходе) |
| Барьерные 400/404 на доменных исключениях | `test_jobs.py` (400 на traversal, 404 на неизвестный проект) |
| Резолв workspace: безопасный сегмент, `.`/`..`, traversal, симлинк | `test_resolve_workspace.py` (24 кейса) |
| Executor не создаёт директорий | `test_resolve_workspace.py`, `test_jobs.py` (404 без mkdir) |
| Потолок вывода с пометкой, без OOM и без зависания | `test_run_job.py` (parametrize stdout/stderr + кейс «в пределах потолка») |
| Прод-фикс GREEN R9: дренаж пайпов с дедлайном (запрос не виснет за переживший процесс) | `test_run_job.py` (кейс деградации капчи) — подтверждён мутацией: снятие маркера красит ровно его |
| Таймаут — результат, не исключение; kill-цепочка | `test_run_job.py` (deadline, внуки), `{T3.7}`, B8 |
| Scrubbed env джобы (B1) | `test_build_job_argv.py` (`--clearenv` + пять `--setenv`), `test_run_job.py` (реальный `env`), `{T3.9}`, B1 |
| `sandbox_enabled=False` → WARNING, дефолт `true` | `test_build_job_argv.py`, `test_settings.py` |
| Три флага kill-контракта, внешний `unshare -n` | `test_build_job_argv.py` (parametrize), `{T3.3}`, `{T3.7}` |
| Изоляция чужих workspace / `/skills` ro (B6b, B7) | `test_build_job_argv.py` (mount-набор), `{T3.3}`, B2/B3/B6c |
| Тулчейн образа (B4), non-root uid (B5) | `{T3.1}`, `{T3.2}`, `{T3.6}`, B5 |
| `EXECUTOR_`-knobs как контракт с compose/env (T1) | `test_settings.py` (11 кейсов) |
| Прод-фикс T3.5: `format_exc_info` в цепочке процессоров | `test_logging.py` (кейс с трейсбеком) — подтверждён мутацией: снятие процессора красит ровно этот кейс |
| Прод-фикс GREEN R1: `exc_info=True` на боевом call-site `job launch failed` | `test_run_job.py` (кейс незапускаемой команды) — подтверждён мутацией: снятие аргумента красит ровно его |
