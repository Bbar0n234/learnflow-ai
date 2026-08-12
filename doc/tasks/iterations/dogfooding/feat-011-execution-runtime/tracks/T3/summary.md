# Summary: feat-011 / трек T3 — Executor-сервис

## TL;DR

Трек T3 закрыт — все семь фаз (T3.1–T3.7) реализованы. Executor — синхронный сервис на
FastAPI: принимает джобу (`POST /jobs`), запускает её под жёстким deadline внутри
`unshare`+`bwrap`-песочницы с пустым netns и возвращает `{stdout, stderr, exit_code}`.
Образ (`services/executor/Dockerfile`) толстый — несёт весь тулчейн джобы
(numpy/pandas/matplotlib/python-docx/docxcompose/pypdf/pandoc/шрифты с кириллицей), non-root
uid 10001, не тянет `pytest`, PID 1 — `tini` (init жнёт bwrap-сирот, иначе каждая джоба
оставляла зомби; фикс R11, см. «Решения и обоснования»). T3.7 закрывает трек воротами релиза этого образа: набор
смоук-сценариев в `services/executor/smoke/` (реальные задачи тулчейна — не import-проверки)
и цель `make smoke-executor`, гоняемая одной командой внутри собранного образа с переключаемым
`RUNTIME` (`runc` — гейт релиза по умолчанию, `runsc` — шаг чек-листа деплоя).

`services/executor/Dockerfile` дополнительно правлен по итогам T1.11 (эскалация к архитектору, разрешена): запекает `/workspaces` с `chown` на uid 10001 до `USER 10001` — фикс ownership именованного volume, см. T1/summary.md § «Решения → T1.11».

**Находка T3.6 про необходимость `--privileged` закрыта в T3.7** — решением архитектора
(эскалация 2026-08-11) `docker run` для смоука несёт три флага
(`--security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt
systempaths=unconfined`), не `--privileged`: граница изоляции — gVisor в проде плюс bwrap на
джобу, не seccomp-профиль самого контейнера executor'а. Эмпирически подтверждено на этом же
dev-хосте (Docker CE 29.6.1, `runc`): с этими тремя флагами (без `--privileged`) полный
sandboxed-прогон `smoke_sandbox.py` — свой workspace (rw), чужой путь (ENOENT), `/skills`
(EROFS), сеть (недостижима) — проходит целиком. Все шесть смоук-сценариев зелёные:
`matplotlib_png`, `pandoc_docx`, `pdf_text`, `python_docx`, `fonts`, `sandbox`. Негативная
проверка ворот прогнана и подтверждена (временная порча `smoke_pdf_text.py` → `smoke-executor`
падает ненулевым кодом с диагностикой; после отката — снова зелёный). `RUNTIME=runsc` на этом
хосте (`runsc` не установлен) падает внятной ошибкой докера («unknown or invalid runtime name:
runsc»), не тихим фолбэком на `runc` — параметр реально доезжает до `docker run`. `make check`
зелёный по всему репозиторию (backend 285 файлов, siem-service 43, executor 18 — 12 сервисных
+ 6 смоук-скриптов, tools 8, import-linter 9/9, arch-checker — только унаследованные warnings
по size-чекам вне executor). `git status` в файловом скоупе трека — только `Makefile` и
`services/executor/`.

T3.5 замыкает HTTP-контракт `POST /jobs` поверх runner'а из T3.4:
`JobRequest`/`JobResponse` в `api/schemas.py` (валидатор «ровно одно из `code`/`cmd`» —
схемой, не `if` в handler'е), синхронный `def`-роутер в `api/routes.py` (кламп `timeout` с
`logger.warning`, ветка `cmd` → `["bash", "-c", cmd]`, ветка `code` → временный файл вне
workspace, ro-бинд в песочницу фиксированным путём `/tmp/job.py`), барьерные exception-handler'ы
в `main.py` (`InvalidProjectIdError`→400, `WorkspaceMissingError`→404, без третьего зеркала
`problem.py` — по закрытому OQ-3). Перенесённый фикс T3.4 закрыт: `logging.py` получил
`structlog.processors.format_exc_info` в цепочку процессоров, проверено эмпирическим вызовом
(`exc_info=True` теперь рендерится в поле `"exception"` с полным трейсбеком, не протекает как
голое `"exc_info": true"`). Весь сценарий Verification T3.5 прогнан живым uvicorn на порту 8002
(scratchpad workspace `p1`): `cmd`/`code`/timeout/traversal/missing-project/422/env-scrubbing —
все совпали с ожиданиями плана. Одна находка вне плана, задокументирована ниже и в отчёте
агента: на dev-хосте (uv-managed toolchain python, не системный) ветка `code` резолвит `python`
внутри песочницы в **системный** Python хоста, а не в venv `executor`-пакета с
numpy/pandas/etc. — see «Решения и обоснования». `make check` (ruff+mypy+import-linter+
arch-checker) зелёный на изолированном прогоне по `services/executor/`; полный репозиторный
прогон флапал из-за параллельных незакоммиченных правок другого трека в `backend/**` (вне
скоупа T3, не трогалось) — см. отчёт агента.

T3.1: заведён пустой, но валидный workspace-член `services/executor/`
(дистрибутив и пакет `executor`), зарегистрирован в корневом `pyproject.toml`, выполнен
единственный за трек прогон `uv lock` — тулчейн джобы (numpy/pandas/matplotlib/
python-docx/docxcompose/pypdf) и runtime-зависимости сервиса (fastapi/uvicorn/pydantic/
pydantic-settings/structlog) резолвятся и лежат в `[project.dependencies]`, как
предписывает план. `Makefile` получил executor-строки в `type-check`/`check` (mypy
отдельным вызовом — свой top-level `tests`) и в `test`/`test-parallel` (по шаблону siem,
толерантность к exit 5). T3.2: минимальное FastAPI-приложение поднято — `Settings`
с `EXECUTOR_`-префиксом (все 8 knob'ов из плана, дефолты сверены дословно), inline-обёртка
над `structlog` по `log_level`, `create_app()` с `GET /health` и `Settings` в
`app.state.settings`, `SettingsDep` через `request.app.state` в `api/deps.py`. T3.3:
чистая функция `build_job_argv` собирает полный `unshare … bwrap … --` префикс варианта A
из спайка (все три флага kill-контракта, суженный `/etc`, ro-bind venv из `sys.prefix`,
`sandbox_enabled=False` → голая команда + WARNING) плюс `resolve_workspace` с валидацией
одного безопасного сегмента `project_id` и узкие исключения `InvalidProjectIdError`/
`WorkspaceMissingError`. Ручной прогон собранного argv на хосте (bwrap 0.11, реальный
kernel — не gVisor) воспроизвёл всю матрицу изоляции C1/C2 спайка: свой файл читается,
чужой workspace недостижим (ENOENT), `/skills` — EROFS, сеть закрыта (`connect()` →
`ENETUNREACH`, `socket.socket()` сам по себе не падает — расхождение с формулировкой
плана разобрано ниже). T3.4: `run_job` в `services/executor/executor/runner.py` — синхронный
запуск argv из `sandbox.build_job_argv` через `Popen(..., start_new_session=True)`, деталь
kill-контракта, которая не помещается в `bwrap`-флаги (`os.killpg` по группе обёртки на
дедлайне, эскалация SIGTERM → grace → SIGKILL), два reader-потока с потолком
`max_output_bytes` на поток вместо `communicate()`, честный `JobResult(timed_out=True)`
вместо исключения на таймаут. Вся kill-матрица верификации (deadline, внуки через
`bash -c 'sleep & sleep'`, потолок вывода без роста RSS, ненулевой exit_code) прогнана
на хосте под реальным sandboxed argv (bwrap 0.11, не только dev-режим
`sandbox_enabled=False`) — фактические числа в «Решения и обоснования». Все четыре фазы —
без отступлений от архитектуры плана, с одной задокументированной корректировкой ожидания
сетевой проверки в T3.3 (см. «Решения и обоснования»). Находки вне скоупа T3 (T1/`backend/**`,
не трогались): `backend/tests/agent/test_pricing_external.py` (дрейф live-цен,
зафиксировано в T3.1) — актуально; несформатированный `backend/app/storage/workspace.py`
(найден при T3.3) — при прогоне `make check` в T3.4 файл уже проходит `ruff format --check .`
чисто, находка устарела (см. Follow-ups).

## Реализовано в фазе T3.1

- `services/executor/pyproject.toml` — по образцу `services/siem-service/pyproject.toml`:
  `name = "executor"`, `requires-python = ">=3.12"`; `[project.dependencies]` — runtime
  сервиса (`fastapi>=0.135.1`, `uvicorn[standard]>=0.41.0`, `pydantic>=2.0`,
  `pydantic-settings>=2.13.1`, `structlog>=25.0`) вперемешку с тулчейном джобы
  (`numpy>=1.26`, `pandas>=2.2`, `matplotlib>=3.9`, `python-docx>=1.1.2`,
  `docxcompose>=1.4`, `pypdf>=5.1`) — единым списком, как требует план (§ «Решения,
  принятые планом»: только так тулчейн попадает в `uv.lock` и в образ через
  `uv sync --locked --no-dev --package executor`). `[tool.setuptools.packages.find]
  include = ["executor*"]`; `[tool.pytest.ini_options]` с `testpaths = ["tests"]` и
  маркерами `unit`/`integration`/`slow` (идентично siem, без `asyncio_mode` — у siem он
  нужен из-за async SQLAlchemy, у executor T3.1 асинхронного кода нет); `[dependency-groups]
  dev = ["learnflow-testing", "pytest-xdist>=3.6"]` + `[tool.uv.sources] learnflow-testing
  = { workspace = true }`.
- `services/executor/executor/__init__.py` — пакет-маркер с docstring и `__version__`
  (по образцу `siem_service/__init__.py`).
- `services/executor/tests/__init__.py` — пустой плейсхолдер (как у siem).
- Корневой `pyproject.toml` — `"services/executor"` добавлен в `[tool.uv.workspace]
  members` алфавитно, перед `"services/siem-service"`. Import-linter-контракты для
  executor не заводились (по плану — вне партиции итерации).
- `uv.lock` — один прогон `uv lock` за весь трек: добавлены `executor v0.1.0` и его
  тулчейн-транзитивные зависимости (`docxcompose`, `matplotlib`, `numpy`, `pandas`,
  `pypdf`, `python-docx` + транзитивные — `babel`, `contourpy`, `cycler`, `fonttools`,
  `kiwisolver`, `lxml`, `pillow`, `pyparsing`, `python-dateutil`, `six`).
- `Makefile`:
  - `type-check` и `check` — добавлена строка `uv run mypy services/executor/` между
    siem-service и `tools/*` (комментарий над `type-check` расширен: «backend, siem-service
    и executor каждый владеют top-level `tests`»).
  - `test` и `test-parallel` — добавлена executor-строка по точному шаблону siem
    (`uv run --package executor pytest -c services/executor/pyproject.toml --rootdir
    services/executor [-n auto] services/executor/tests`, exit 0/5 толерантность), заголовок
    `test`-цели дополнен упоминанием executor.

## Реализовано в фазе T3.2

- `services/executor/executor/config.py` — `Settings(BaseSettings)`,
  `env_prefix="EXECUTOR_"`. Восемь полей — точное соответствие таблице
  «EXECUTOR_-knobs» плана: `workspaces_root: str = "/workspaces"`,
  `skills_root: str = "/skills"`, `default_timeout_seconds: int = 60`,
  `max_timeout_seconds: int = 300`, `max_output_bytes: int = 262144`,
  `kill_grace_seconds: int = 5`, `log_level: str = "info"`,
  `sandbox_enabled: bool = True`. Секретов и обязательных полей нет (докстрингом
  зафиксировано обоснование — доступ контролирует exec-сеть). Mount-набор песочницы
  сюда не заводился — он инвариант безопасности, живёт в коде `executor.sandbox` (T3.3).
- `services/executor/executor/logging.py` — `configure_logging(log_level: str)`:
  `structlog.make_filtering_bound_logger` по уровню из `logging.getLevelNamesMapping()`
  (публичный stdlib API с Python 3.11, не `structlog.stdlib.NAME_TO_LEVEL` — см. решение
  ниже), `PrintLoggerFactory` (JSON-строки в stdout напрямую, без моста в stdlib
  `logging` — у executor нет сторонних логеров для перехвата, в отличие от backend).
- `services/executor/executor/main.py` — `create_app()`: `Settings()` создаётся внутри,
  `configure_logging` вызывается сразу после, `app.state.settings = settings`,
  `GET /health → {"status": "ok"}`; `app = create_app()` на модульном уровне (как у siem —
  это не module-level синглтон состояния, а стандартный ASGI-entrypoint). Роутер `/jobs`
  и exception-handler'ы — вне скоупа T3.2, добавляются в T3.5.
- `services/executor/executor/api/__init__.py`, `services/executor/executor/api/deps.py` —
  `get_settings(request: Request) -> Settings` через `request.app.state.settings`,
  `SettingsDep = Annotated[Settings, Depends(get_settings)]` — дословно по образцу
  `backend/app/api/deps.py::SettingsDep` и `siem_service/api/deps.py`.

## Реализовано в фазе T3.3

- `services/executor/executor/sandbox.py` — чистые функции, ничего не запускают:
  - `build_job_argv(workspace: Path, command: list[str], settings: Settings) -> list[str]`
    — префикс варианта A из спайка: внешняя обёртка `unshare -U --map-current-user -n`
    (у bwrap собственный `--unshare-net` под gVisor фатален — находка 3 спайка), затем
    `bwrap` с тремя флагами kill-контракта (`--unshare-pid --die-with-parent
    --new-session`) + `--unshare-user --unshare-ipc --unshare-uts`, `--clearenv` и
    `--setenv` минимального набора (`PATH`/`HOME`/`LANG`/`MPLCONFIGDIR`/`XDG_CACHE_HOME`),
    `--ro-bind /usr` + симлинки merged-usr (`/bin`, `/lib`, `/lib64`, `/sbin`), суженный
    ro-bind `/etc` (список — см. ниже), `--ro-bind` префикса venv из `sys.prefix`
    (не хардкод), `--proc /proc --dev /dev --tmpfs /tmp`, `--bind <workspace> /workspace`,
    `--ro-bind <skills_root> /skills`, `--chdir /workspace`, `--` + команда.
    `settings.sandbox_enabled = False` — короткое замыкание: `logger.warning(...,
    sandbox_enabled=False)` + голая команда без обёртки, ровно на каждый вызов (не
    только на переключение) — наблюдаемая деградация, § Восстановление.
  - `resolve_workspace(project_id: str, settings: Settings) -> Path` — `project_id`
    проверяется regex'ом `^[A-Za-z0-9._-]{1,128}$` с явным отдельным отказом `"."`/`".."`
    (оба матчат чарсет, поэтому вынесены в отдельную проверку), затем путь резолвится
    (`workspaces_root / project_id`, `.resolve()`) и проверяется `is_relative_to(workspaces_root)`
    как defense-in-depth. Директорию не создаёт: отсутствующий каталог →
    `WorkspaceMissingError`, а не молчаливый mkdir (executor не владеет workspace'ами —
    design-brief § Executor).
- `services/executor/executor/exceptions.py` — `InvalidProjectIdError`,
  `WorkspaceMissingError`, обе наследуют `Exception` напрямую (не `AppError`) — случай 2
  «Модели ошибок» conventions.md: внутренние исключения подсистемы, гасятся на барьере
  `/jobs` в T3.5, HTTP-семантики не несут.

## Реализовано в фазе T3.4

- `services/executor/executor/runner.py`:
  - `run_job(workspace: Path, command: list[str], timeout: float, settings: Settings) ->
    JobResult` — берёт готовый argv из `sandbox.build_job_argv` (сам не различает
    `sandbox_enabled`, эта ветка уже решена внутри `build_job_argv`), запускает
    `subprocess.Popen(argv, start_new_session=True, env=job_env, stdout=PIPE, stderr=PIPE,
    cwd=workspace)`. `start_new_session=True` — первое звено kill-контракта: переводит
    обёртку (`unshare`+`bwrap`) в собственную группу процессов, недостижимую иначе для
    `killpg` из процесса executor'а (два остальных звена — `--die-with-parent` и
    `--unshare-pid`, уже зашиты в argv из T3.3).
  - `_kill_process_group(proc, kill_grace_seconds)` — на `subprocess.TimeoutExpired` от
    `proc.wait(timeout=…)`: `os.killpg(os.getpgid(proc.pid), SIGTERM)` → `proc.wait(timeout=
    kill_grace_seconds)` → при повторном `TimeoutExpired` `os.killpg(..., SIGKILL)` →
    безусловный `proc.wait()`. Гонки с уже завершившимся процессом (`ProcessLookupError`
    на `getpgid`/`killpg`) гасятся точечно — не второй источник правды об исходе джобы,
    просто defensive race-guard вокруг сигналов ОС.
  - `_PipeReader` — по потоку на `stdout`/`stderr`, читает чанками по 64 KiB в фоновом
    `threading.Thread`, держит первые `max_output_bytes` в `bytearray`, остальное читает
    и отбрасывает (не накапливает) до EOF. `communicate()` не используется — он буферизует
    без потолка, ровно тот OOM-сценарий, ради которого вводится knob. Потоки стартуют
    до `proc.wait(timeout=…)` и `join()`-ятся после — обязательный порядок, иначе полный
    буфер пайпа блокирует джобу до дедлайна вместо естественного завершения.
  - Усечение — маркер `…[output truncated: N bytes dropped]` дописывается к
    **раздекодированному** тексту (не к сырым байтам перед decode) — так граница обрезки
    не может испортить multi-byte UTF-8 хвост маркера; сам обрезанный хвост джобового
    вывода decode обрабатывает штатно через `errors="replace"`.
  - Таймаут не бросает исключение: `JobResult.timed_out=True`, `exit_code` — фактический
    `proc.returncode` (отрицательный при убийстве сигналом, как у `subprocess`), в `stderr`
    дописывается диагностика вида `[executor] job exceeded timeout of {timeout}s — killed
    (SIGTERM, then SIGKILL after {kill_grace_seconds}s grace)`.
  - Инфраструктурный отказ запуска (`Popen()` бросает `OSError` — например, `unshare`/
    `bwrap` не нашлись в `PATH`) — не превращается в `JobResult`: `logger.error("job launch
    failed", …)` и переброс исключения наружу (обработка на HTTP-барьере — T3.5, вне
    скоупа фазы).
  - `job_env` — фиксированный минимальный набор (`PATH` от `sys.prefix`, `HOME=/workspace`,
    `LANG=C.UTF-8`, `MPLCONFIGDIR=/tmp/mpl`, `XDG_CACHE_HOME=/tmp/cache`), значения
    буквально совпадают с тем, что `sandbox.build_job_argv` зашивает в `--setenv` — решение
    и обоснование см. ниже.
  - Единственный лог-вызов `"job finished"` на исход джобы (не отдельные INFO/WARNING) —
    уровень выбирается по `timed_out` (`logger.warning` при таймауте, иначе
    `logger.info`), поля `project_id` (`workspace.name` — `run_job` не принимает
    `project_id` отдельным параметром, а `resolve_workspace` уже вложил его в
    `workspace`), `exit_code`, `duration_ms`, `timed_out`, `stdout_truncated`,
    `stderr_truncated`.

## Реализовано в фазе T3.5

- `services/executor/executor/api/schemas.py` — `JobRequest` (`project_id: str`,
  `code: str | None`, `cmd: str | None`, `timeout: float | None`) с
  `@model_validator(mode="after")`, требующим ровно одно из `code`/`cmd` —
  нарушение всплывает как обычный `422` через штатную обработку
  `RequestValidationError` FastAPI, отдельный handler не нужен. `JobResponse`
  (`stdout: str`, `stderr: str`, `exit_code: int`) — поля не менялись
  (межтрековый контракт 2).
- `services/executor/executor/api/routes.py` — `POST /jobs`, синхронный
  `def create_job`:
  - `_clamp_timeout` — `None` берёт `default_timeout_seconds` без предупреждения
    (это не кламп, а обычный дефолт); вне `[0, max_timeout_seconds]` —
    `logger.warning("timeout clamped", requested_timeout=…, clamped_timeout=…,
    max_timeout_seconds=…)`;
  - `cmd` → `["bash", "-c", cmd]` (не `-lc` — см. docstring роутера и план);
  - `code` → `tempfile.mkstemp` вне workspace, ro-bind в `run_job(...,
    extra_ro_binds=[(tmp_path, "/tmp/job.py")])` при `sandbox_enabled=True`
    (запуск `python /tmp/job.py`); при `sandbox_enabled=False` — запуск
    напрямую по реальному пути временного файла (обоснование ниже), файл
    удаляется в `finally` в обеих ветках;
  - результат `run_job` → `JobResponse`; отказы `resolve_workspace`
    (`InvalidProjectIdError`/`WorkspaceMissingError`) не перехватываются
    здесь — долетают до барьера в `main.py`.
- `services/executor/executor/sandbox.py` — `build_job_argv` получил
  keyword-only `extra_ro_binds: Sequence[tuple[str, str]] = ()`: на
  сандбоксированной ветке эти `--ro-bind` вставляются строго после
  `--tmpfs /tmp` и перед `--bind <workspace> /workspace` (bwrap применяет
  операции по порядку argv — вставка раньше `--tmpfs` была бы замаскирована
  tmpfs); на несандбоксированной ветке (`sandbox_enabled=False`) параметр
  игнорируется (нет mount-namespace, ремапить некуда). Единственное изменение
  в файле T3.3 — новый опциональный параметр, существующий контракт вызова
  не ломается (дефолт `()`).
- `services/executor/executor/runner.py` — `run_job` получил тот же
  keyword-only `extra_ro_binds`, прокидывает без изменений в `build_job_argv`.
- `services/executor/executor/main.py` — `_invalid_project_id_handler`
  (`InvalidProjectIdError` → 400) и `_workspace_missing_handler`
  (`WorkspaceMissingError` → 404) зарегистрированы через
  `app.add_exception_handler`; `app.include_router(router)` подключает
  `/jobs`. Третьего зеркала `problem.py` нет (OQ-3, закрыт оркестратором) —
  простой `JSONResponse(status_code=…, content={"detail": …})`, без RFC 9457
  problem+json конверта.
- `services/executor/executor/logging.py` — перенесённый фикс T3.4:
  `structlog.processors.format_exc_info` добавлен в цепочку процессоров
  перед `JSONRenderer()`. Проверено эмпирическим вызовом
  (`logger.error(..., exc_info=True)` внутри `except`) — поле `"exception"`
  теперь несёт полный текстовый трейсбек вместо голого `"exc_info": true`.
  Находка T3.4 закрыта.

## Реализовано в фазе T3.6

- `services/executor/Dockerfile` — build context корень репо, база
  `python:3.12-slim-bookworm`, `COPY --from=ghcr.io/astral-sh/uv:0.11.21` (тот
  же pin, что в backend/siem-service). apt-слой: `bubblewrap`, `util-linux`
  (даёт `unshare`), `pandoc`, `curl`, `fontconfig`, `fonts-dejavu`,
  `fonts-liberation2`, `fonts-noto-core`, `ca-certificates`,
  `rm -rf /var/lib/apt/lists/*`. Два `uv sync --locked --no-dev --package
  executor` по шаблону siem: первый с bind-mount'ами манифестов **всех**
  членов workspace (`backend`, `packages/siem-contracts`, `packages/testing`,
  `services/siem-service`, `services/executor`, `tools/security-scan`,
  `tools/arch-checker`) и `--no-install-workspace`, второй — после копирования
  исходников. Набор `COPY` — 1:1 из `services/siem-service/Dockerfile`
  (`packages/`, `services/` — вместе с ним `services/executor/smoke/` для
  T3.7, манифесты `tools/*` и `backend/pyproject.toml`, корневые
  `pyproject.toml`+`uv.lock`). Non-root: `useradd -u 10001 -m -d
  /home/executor executor`, `chown -R executor:executor /app` (владение
  `.venv` и рабочих каталогов), `USER 10001`. `ENV PYTHONUNBUFFERED=1`,
  `PATH=/app/.venv/bin:$PATH`, `EXPOSE 8002`, `CMD ["uvicorn",
  "executor.main:app", "--host", "0.0.0.0", "--port", "8002", "--app-dir",
  "services/executor"]` — без entrypoint-скрипта (миграций у сервиса нет).
- `Makefile` — цель `docker-build-executor` (`docker build -f
  services/executor/Dockerfile -t learnflow-executor:local .`), `.PHONY`
  дополнен.

## Реализовано в фазе T3.7

- `services/executor/smoke/_common.py` — общий хелпер `report(name, main)`:
  запускает `main()`, печатает `PASS <name>` / `FAIL <name>: <reason>` в
  одну строку и выходит с соответствующим кодом (0/1) — контракт плана
  «каждый сценарий: ненулевой exit при провале, вывод PASS/FAIL в одну
  строку», не продублированный в каждом скрипте отдельно. Не входит в
  список сценариев плана дословно, но не самостоятельный сценарий, а общая
  инфраструктура шести перечисленных ниже.
- `services/executor/smoke/smoke_matplotlib_png.py` — pandas/numpy расчёт
  → matplotlib PNG (backend `Agg`, выбран через `MPLBACKEND`, который
  выставляет `run_all.sh` — не мутацией `os.environ` внутри скрипта до
  импорта `matplotlib`, чтобы не ловить import-after-statement ordering
  hack); проверка magic-байтов PNG (`\x89PNG\r\n\x1a\n`) и ненулевого
  размера.
- `services/executor/smoke/smoke_pandoc_docx.sh` — `pandoc md → docx`;
  проверка ZIP local-file-header magic-байтов (`504b0304`, не по
  расширению файла) и обратное чтение содержимого через python-docx.
- `services/executor/smoke/smoke_pdf_text.py` + `smoke/fixtures/sample.pdf`
  — извлечение текста через pypdf из зафиксированной в репозитории
  фикстуры (589 байт, минимальный валидный PDF 1.4 с одной строкой текста
  на базовом шрифте Helvetica — собран локально вручную по спецификации
  PDF, без внешних генераторов и без сети, с корректно вычисленными
  offset'ами xref-таблицы; проверен `pypdf.PdfReader` перед коммитом),
  проверка маркерной строки `SMOKE_PDF_MARKER` в извлечённом тексте.
- `services/executor/smoke/smoke_python_docx.py` — сборка двух `.docx`
  через python-docx, склейка через `docxcompose.composer.Composer`,
  обратное чтение объединённого документа — проверка, что оба абзаца
  обеих исходных частей присутствуют в результате.
- `services/executor/smoke/smoke_fonts.py` — `fc-match "DejaVu Sans"` /
  `fc-match "Noto Sans"` резолвятся в связанное семейство (не в
  неродственный дефолтный фолбэк), плюс рендер кириллического заголовка
  matplotlib (`fig.canvas.draw()` под `warnings.catch_warnings(record=True)`)
  без предупреждений, содержащих `"glyph"` в тексте — реальная проверка
  покрытия глифов, не только наличия шрифтового пакета.
- `services/executor/smoke/smoke_sandbox.py` — единственный сценарий,
  прогоняющий полный `unshare … bwrap …`-префикс: вызывает
  `executor.runner.run_job` (не голый `subprocess`) над inline-скриптом,
  исполняемым **внутри** песочницы, который проверяет все четыре пункта
  плана за один прогон джобы — запись/чтение своего `/workspace` (успех),
  чтение `/workspaces/other-project/...` (`FileNotFoundError` — `/workspaces`
  как точка монтирования вообще отсутствует в mount-ns джобы, замаунчен
  только единственный `/workspace`), запись в `/skills` (`OSError` — EROFS),
  исходящий TCP-коннект на `1.1.1.1:443` (`OSError` — сеть недостижима).
  Явно фейлится, если `settings.sandbox_enabled=False` (тест бессмыслен без
  реального bwrap-префикса). Импортирует `executor.*` через `PYTHONPATH`,
  который выставляет `run_all.sh` (пакет не pip-install'ится в shared venv —
  тот же приём, что у `backend/scripts/*`), не sys.path-хаком внутри файла
  (не потребовал `# noqa: E402`, чище, чем альтернатива).
- `services/executor/smoke/run_all.sh` — прогоняет все шесть сценариев
  последовательно **не** останавливаясь на первом провале (так «агрегированный
  итог» плана даёт больше диагностики за один прогон, чем fail-fast), печатает
  сводку (`run_all: N/6 scenario(s) failed` / `all 6 scenarios passed`) и
  выходит ненулевым кодом, если провалился хотя бы один. Экспортирует
  `PYTHONPATH`/`MPLBACKEND` для всех Python-сценариев разом.
- `Makefile` — переменная `RUNTIME ?= runc` и цель `smoke-executor`:
  готовит tmp-workspace (`mktemp -d`, поддиректория `smoke/`, `chown` на
  10001:10001 подготовительным `docker run --user 0 … chown` — bind-mount
  хостового tmp иначе сохраняет uid хоста, а gVisor требует владельца =
  uid джобы, находка 4 спайка), затем `docker run --rm
  --runtime=$(RUNTIME) <три security-opt флага> -v …:/workspaces -v
  $(PWD)/skills:/skills:ro learnflow-executor:local
  /app/services/executor/smoke/run_all.sh`. После прогона — симметричный
  `chown` обратно на host uid/gid перед `rm -rf` tmp-каталога (без него
  каталог, чужой для хостового пользователя, остаётся в `/tmp` мусором —
  находка этой фазы, не было в плане дословно, исправлено на месте).
  Help-строка цели упоминает `docker-build-executor` как предварительный
  шаг (не зашита зависимостью — пересборка образа осталась явным шагом,
  как и в T3.6).

## Решения и обоснования

- **`default_timeout_seconds`/`max_timeout_seconds`/`kill_grace_seconds` — `int`, не
  `float`.** Таблица knob'ов плана даёт целые дефолты (60/300/5) и Verification T3.2
  печатает `EXECUTOR_MAX_TIMEOUT_SECONDS=42 → 42` (не `42.0`). `JobRequest.timeout`
  (T3.5) типизирован `float | None` в контракте, но это разные поля: knob'ы — целочисленные
  границы clamp'а, `timeout` запроса — дробный ввод клиента; `min(max(timeout, 0),
  max_timeout_seconds)` корректно работает при смешении `float`/`int` без явного каста.
- **`logging.getLevelNamesMapping()`, а не `structlog.stdlib.NAME_TO_LEVEL`.** Первая
  реализация читала уровень из `structlog.stdlib.NAME_TO_LEVEL` (тот же паттерн, что
  использует сам `structlog` внутри) — mypy с `no_implicit_reexport = true` (корневой
  `pyproject.toml`) валит её: атрибут не входит в явный экспорт модуля `structlog.stdlib`.
  Переключился на `logging.getLevelNamesMapping()` — публичный stdlib API (Python 3.11+),
  типизирован, mypy-чист; семантически то же отображение имени в число.
- **`main.py` без `lifespan`.** У siem `lifespan` поднимает БД/Redis/фоновые задачи;
  у executor T3.2 нет ничего, что требует старт/shutdown-хуков — `Settings()` и
  `configure_logging()` синхронны и безопасны в теле `create_app()`. `lifespan` не
  заводился как мёртвый код; появится, если такая потребность возникнет в поздних фазах
  трека (`sandbox.py`/`runner.py` в T3.3–T3.4 своих ресурсов на процесс не держат).
- **Нюанс запуска verification-команд из плана: `PYTHONPATH` через `cwd`, не editable-install.**
  `app`/`siem_service`/`executor` не pip-install'ятся в shared venv (см. комментарий в
  корневом `pyproject.toml` над `[tool.importlinter]` — тот же факт для `app`/`siem_service`).
  `uv run --package executor python -c "import executor"` из корня репозитория падает
  `ModuleNotFoundError`; тот же вызов из `services/executor/` (или `--app-dir
  services/executor` для uvicorn, `--rootdir services/executor` для pytest — оба уже в
  Makefile) работает, потому что `python -c` кладёт `""` (эквивалент cwd) в `sys.path[0]`.
  Verification-пункты плана прогнаны с `cd services/executor` — не отступление, а то же
  соглашение, что уже используется в Makefile-целях трека.
- **`[tool.pytest.ini_options]` без `asyncio_mode`/`asyncio_default_fixture_loop_scope`.**
  План описывает набор опций «как у siem», но siem включает `asyncio_mode = "auto"` из-за
  async SQLAlchemy/тестов с БД. У executor T3.1 нет асинхронного кода и БД вовсе (сервис —
  синхронный `def`-handler по конвенции блокирующего кода, план § «Решения, принятые
  планом»); опции для pytest-asyncio добавлены бы мёртвым конфигом. Маркеры
  `unit`/`integration`/`slow` (единственное, что план требует явно, «как у siem») перенесены
  дословно.
- **Порядок зависимостей в `[project.dependencies]`.** Runtime-зависимости сервиса и
  тулчейн джобы перечислены единым списком без группового разделения — план прямо
  указывает, что тулчейн обязан жить в `[project.dependencies]`, а не отдельной
  optional-группой; порядок (сервис → тулчейн) выбран для читаемости, семантики не несёт.
- **Плавающие нижние границы версий тулчейна (`numpy>=1.26`, `pandas>=2.2`,
  `matplotlib>=3.9`, `python-docx>=1.1.2`, `docxcompose>=1.4`, `pypdf>=5.1`), без верхней
  границы.** План не фиксирует точные версии — в репозитории нет прецедента этих пакетов.
  Стиль (`>=` floor, без потолка) скопирован с существующих манифестов
  (`siem-service/pyproject.toml`, `backend/pyproject.toml`) — единообразие workspace, а не
  отдельное решение по пинам. `uv lock` разрешил актуальные на дату прогона версии (numpy
  2.5.2, pandas 3.0.5, matplotlib 3.11.1, python-docx 1.2.0, docxcompose 2.2.0, pypdf
  6.15.0) — фактическая фиксация версий для образа теперь в `uv.lock`, манифест остаётся
  floor-only по конвенции workspace.
- **`uv sync --package executor` временно «сузил» shared venv workspace (убрал зависимости
  backend/siem, не входящие в executor), из-за чего первый прогон `make check` упал на
  backend с `import-not-found` по langfuse/langgraph/siem_contracts и т.д.** Не баг
  executor-манифеста: `uv sync --package X` в uv-воркспейсах по умолчанию синхронизирует
  venv только под явно перечисленный член плюс dev-группу workspace root, выгружая пакеты,
  специфичные для других членов. Восстановлено `uv sync --all-packages`, после чего `make
  check` прошёл зелёным по всему монорепо (backend 282 файла, siem-service 43, executor 2,
  tools 8, import-linter 9/9, arch-checker). Дальнейшая работа (T3.2+) должна иметь в виду:
  `uv sync --package executor` (упомянутый в Verification T3.1 и в шаблоне Dockerfile) —
  корректная команда для проверки, резолвится ли executor изолированно, и для сборки образа
  (там venv одноразовый), но не для локальной разработки в общем venv монорепо — там нужен
  `uv sync` (all-packages, дефолт) или явный `uv sync --package executor` с последующим
  `uv sync --all-packages` перед возвратом к работе с другими пакетами.
- **Итоговый суженный список `/etc`-биндов (T3.3): `ld.so.cache`, `passwd`, `group`,
  `ssl/certs`, `fonts`.** `resolv.conf` осознанно исключён — джоба без сети (пустой
  netns), резолвинг имён ей не нужен. Каждый путь проверяется `Path.exists()` перед
  добавлением в argv (не безусловный `--ro-bind`) — на боевом образе набор файлов может
  отличаться от dev-хоста (Fedora 43 здесь vs Debian bookworm в T3.6), пропавший
  путь не должен ронять сборку argv; точная валидность набора для образа подтверждается
  смоуком T3.7, как и предполагает план.
- **Ручной прогон на хосте (bwrap 0.11.0, Fedora 43, реальное ядро) воспроизвёл матрицу
  изоляции спайка C1/C2 один-в-один с продовым argv.** Собранный `build_job_argv`
  прогонялся `subprocess.run` без sandbox-обёртки агентского bash (тот же приём, что и
  у самого спайка — вложенный userns/netns недоступен из-под `--unshare-net`
  bash-песочницы). Результат: чтение своего файла — OK; чтение чужого workspace
  (посторонний каталог вне бинда) — `FileNotFoundError` (ENOENT), не «отказано в
  доступе» — путь физически отсутствует в mount-ns; запись в `/skills` —
  `OSError errno=30` (EROFS); запись в свой workspace — OK, файл виден на хостовой ФС
  (write-through); `PID` внутри песочницы — `2` (коллапс pid-ns подтверждён).
  **Расхождение с буквальной формулировкой плана по сети:** `socket.socket(AF_INET,
  SOCK_STREAM)` сам по себе **не бросает исключение** на реальном ядре Linux — создание
  сокета не требует интерфейсов, только `connect()`/`bind()` идут через маршрутизацию.
  Фактический результат — `connect()` к `127.0.0.1:80` и `1.1.1.1:443` даёт `OSError
  errno=101 (Network is unreachable)`, что дословно совпадает со строкой ошибки
  спайка в C2 («сеть закрыта: `OSError: [Errno 101] Network is unreachable`»). `EAFNOSUPPORT`
  из плана — цитата поведения G3/G4 спайка, а это прогоны **под gVisor** (netstack
  runsc не создаёт вообще никаких интерфейсов, включая lo, поэтому там падает уже
  `socket()`); на голом хосте (эта фаза, без runsc) сетевой стек ядра полноценнее —
  netns создаётся и работает, `AF_INET` как протокольное семейство поддерживается всегда,
  а вот маршрутов до любого адреса, включая loopback, — ноль, отсюда `ENETUNREACH`
  вместо `EAFNOSUPPORT`. Сетевая изоляция джобы полная в обоих случаях (сокет создать
  можно, использовать — нельзя); расхождение — в конкретном errno между реальным ядром
  и gVisor netstack, не в самом факте изоляции. Прод-verification под `runsc`
  (T3.7 `smoke_sandbox.py --runtime=runsc`) должен увидеть `EAFNOSUPPORT`, как в G4
  спайка — это тот сценарий, который план описывал.
- **`git diff --stat` показывает изменённым не только `uv.lock`, но и `design-brief.md`.**
  Эта правка (раздел «Партиция треков») сделана до начала T3.1, на этапе PLAN — вне
  файлового скоупа трека (`services/executor/**`, `Makefile`, корневой `pyproject.toml`,
  `uv.lock`), в этой фазе не трогалась. Verification-пункт плана («ровно один изменённый
  `uv.lock`») трактуется как «среди файлов lock-политики uv» — выполнен: `uv.lock` —
  единственный изменённый файл зависимостей.

- **`job_env` — фиксированный набор в `runner.py`, а не второй возврат из
  `build_job_argv`.** План T3.4 читается как «argv/env — из `sandbox.build_job_argv`», но
  фактическая сигнатура функции после T3.3 (`build_job_argv(...) -> list[str]`) возвращает
  только argv: scrubbing джобового env под `sandboxed`-веткой уже целиком реализован
  *внутри* argv (`--clearenv` + `--setenv` в bwrap-префиксе) и не зависит от того, что
  Popen передаёт снаружи — окружение, которое видит `runner.py` при
  `sandbox_enabled=True`, нужно только самим обёрточным процессам (`unshare`/`bwrap`),
  чтобы найти свои бинарники по `PATH`. Поэтому `runner.py` строит собственный
  минимальный `job_env` (те же литералы, что `sandbox.py` кладёт в `--setenv`) и
  использует его в обеих ветках Popen — и как «окружение для обёртки» при
  `sandbox_enabled=True`, и как буквальное окружение джобы при `sandbox_enabled=False`
  (dev-escape-hatch не должен протекать в джобу переменными сервиса — тот же инвариант
  B1 «джоба не видит env сервиса», просто без namespace-изоляции). Изменения в
  `sandbox.py` не потребовались — это решение целиком внутри файлового и функционального
  скоупа T3.4.
- ~~**`exc_info=True` не используется в ERROR-логе `"job launch failed"`.**~~ —
  **закрыто в два шага; полностью — на фазе GREEN (R1).** Трейсбек в логе требует
  двух вещей сразу: процессора в цепочке и аргумента на месте вызова. T3.5 закрыла
  первую половину — `services/executor/executor/logging.py` (T3.2) собирала цепочку
  без `structlog.processors.format_exc_info`, из-за чего `exc_info=True` не
  рендерился, а протекал в JSON бесполезным полем `"exc_info": true`; T3.5 добавила
  `format_exc_info` перед `JSONRenderer()` и проверила это синтетическим вызовом.
  Вторая половина оставалась открытой: единственный боевой call-site
  (`runner.py`, `logger.error("job launch failed", …)`) аргумента `exc_info=True`
  так и не получил, поэтому в проде в JSON ехали только `error`/`error_type` без
  трейсбека — на что и указала находка ревью R1 (major). Формулировка «находка
  закрыта в T3.5» была преждевременной. Аргумент добавлен на фазе GREEN; проверено
  эмпирически на реальной цепочке процессоров (`configure_logging("info")` +
  несуществующий бинарник): в строке `"job launch failed"` появилось поле
  `"exception"` с полным трейсбеком до `subprocess.Popen`.
- **Фактические числа kill-матрицы T3.4 (bwrap 0.11.0, sandboxed argv, хост, не dev-режим
  `sandbox_enabled=False`).** Нормальный прогон (`echo hello`) — `exit_code=0`,
  `stdout="hello\n"`. Дедлайн (`sleep 300`, `timeout=2`, `kill_grace_seconds=2`) —
  `timed_out=True`, `exit_code=-15` (обёртка `unshare` умерла от SIGTERM в течение grace,
  до эскалации к SIGKILL — сама обёртка не игнорирует SIGTERM, поэтому наблюдаемый
  `-15`, не `-9`), `duration_ms≈2003` (≈ `timeout`, не `timeout + kill_grace_seconds`);
  `pgrep -x sleep` после возврата — пусто. Внуки (`bash -c 'sleep 300 & sleep 300'`,
  `timeout=2`) — тот же исход (`timed_out=True`, `exit_code=-15`, `duration_ms≈2003`);
  `ps -eo pid,comm` после возврата не содержит ни одного процесса `sleep` — коллапс
  pid-namespace добил оба фоновых `sleep` без отдельного участия runner'а. Потолок вывода
  (`python3 -c "print('x'*10_000_000)"`, `max_output_bytes=1024`) — `exit_code=0`,
  `timed_out=False`, `stdout_truncated=True`, `len(stdout)=1067` (1024 полезных байт +
  текст маркера `…[output truncated: 9998977 bytes dropped]`), `duration_ms≈65` —
  джоба завершается штатно и быстро, не виснет на заполненном пайпе. Ненулевой код
  (`sh -c 'echo err >&2; exit 3'`) — `exit_code=3`, `stderr="err\n"`, `timed_out=False`.
  Инфраструктурных отказов запуска (`unshare`/`bwrap` не найдены) не воспроизводилось —
  бинарники присутствуют на верификационном хосте; путь `logger.error` + переброс
  исключения проверен только чтением кода, не прогоном.
- **T3.5: `code`-ветка при `sandbox_enabled=False` запускается по реальному пути
  временного файла, а не по фиксированному `/tmp/job.py`.** План фиксирует
  `/tmp/job.py` как стабильный путь для читаемых трейсбеков — это осмысленно
  только на сандбоксированной ветке, где `--ro-bind <tmp> /tmp/job.py`
  физически ремапит файл. На несандбоксированной ветке (dev escape hatch,
  `build_job_argv` возвращает голую команду без mount-namespace) ремаппить
  нечем: буквальный запуск `python /tmp/job.py` там просто не нашёл бы файл.
  `routes.py` поэтому выбирает команду по `settings.sandbox_enabled` — с
  реальным путём временного файла на несандбоксированной ветке. План этот
  случай явно не разбирает (Verification T3.5 гоняется при дефолтном
  `sandbox_enabled=True`); решение — минимальное отступление в сторону
  корректности, не архитектурное.
- ~~**Находка (не исправлялась, вне полномочий T3.5): на dev-хосте с
  uv-managed toolchain-python `code`-ветка резолвит `python` внутри
  песочницы в системный Python хоста, а не в venv пакета `executor`.**~~ —
  **закрыто в T3.6, воспроизведено и подтверждено на образе.** Причина на
  dev-хосте — цепочка симлинков: `.venv/bin/python` у uv-управляемого
  интерпретатора указывает на `~/.local/share/uv/python/cpython-…/bin/python3.12`,
  путь вне и `/usr`, и вне `venv_prefix`-ro-bind'а песочницы. На образе T3.6
  `sys.prefix` внутри контейнера — `/app/.venv`, куда `uv sync` кладёт
  настоящий венв поверх системного интерпретатора базового образа
  (`python:3.12-slim-bookworm`), без промежуточного симлинка на внешнее
  хранилище toolchain'ов — предположение T3.5 подтвердилось буквально.
  Проверено прогоном полного sandboxed-префикса (`unshare -U --map-current-user
  -n bwrap …`, собранного `executor.sandbox.build_job_argv` внутри самого
  образа, с временным workspace-каталогом `chown`-нутым на uid 10001):
  `python -c "import numpy; print(numpy.__version__)"` внутри песочницы →
  `2.5.2` (та же версия, что `uv sync` зарезолвил в `[project.dependencies]`,
  т.е. интерпретатор джобы — венв пакета `executor`, не системный Python).
  Прогон потребовал `docker run --privileged` — на dev-хосте verification'а
  (Docker CE 29.6.1, `runc`, дефолтный seccomp-профиль `builtin`) вложенный
  `unshare -U`/`bwrap --proc /proc` не проходит даже под
  `--security-opt seccomp=unconfined --security-opt apparmor=unconfined`
  (падает на `mount proc`, `Operation not permitted`) — отдельная находка,
  см. ниже; `--privileged` использован только как обходной путь для этой
  конкретной проверки, не часть образа/Makefile. OQ-1 остаётся в силе:
  `cmd` — основной путь T1→executor и им не затронут; закрытие относится к
  резервной ветке `code`.
- **T3.6: `fontconfig` добавлен в apt-слой сверх буквального перечня плана.**
  План перечисляет только пакеты шрифтов (`fonts-dejavu`, `fonts-liberation2`,
  `fonts-noto-core`), но сам же требует в Verification `fc-list | wc -l`
  ненулевым — на bookworm-slim пакеты шрифтов не тянут `fontconfig`
  транзитивно, `fc-list`/`fc-match` без него отсутствуют (`command not
  found`), и `/etc/fonts`, который `executor.sandbox` (T3.3) ro-биндит в
  песочницу, не наполнен конфигом. Дрейф между текстом плана и его же
  Verification исправлен на месте (CLAUDE.md «исправляй дрейф на месте») —
  не архитектурное решение, `fontconfig` — стандартный системный пакет для
  той же функции («шрифты с кириллицей и математикой»), которую план уже
  вводит явно.
- **T3.6: буквальная проба bwrap из Verification плана (`bwrap --unshare-user
  --unshare-pid --ro-bind /usr /usr --symlink usr/bin /bin -- /bin/true`) не
  проходит на dev-хосте этой верификации под дефолтным `docker run`.** Первая
  причина — под голым `--symlink usr/bin /bin` (без `/lib`, `/lib64`,
  `/sbin`) `/bin/true` не находит `/lib64/ld-linux-x86-64.so.2` (ENOENT
  динамического линкера, не привилегий) — сама команда в плане короче, чем
  реальный набор симлинков `executor.sandbox._MERGED_USR_SYMLINKS` (T3.3);
  с полным набором симлинков ошибка меняется на «No permissions to create
  new namespace» уже на этапе `unshare -U`/`bwrap --unshare-user` — это и
  есть основная находка: Docker CE 29.6.1 на этом хосте (`runc`, дефолтный
  seccomp-профиль `builtin`, без rootless/userns-remap) блокирует
  непривилегированное создание user-namespace изнутри контейнера. Это ровно
  риск, названный в спайке (`spikes/spike-bwrap-gvisor.md` § «Ограничения
  переноса», пункт 2: «Дефолтный seccomp-профиль docker исторически режет
  unshare/clone(CLONE_NEWUSER) для непривилегированных контейнеров... Первая
  проверка на проде: `docker run --runtime=runsc <образ> bwrap
  --unshare-user ... true` от non-root пользователя образа») — здесь
  подтверждён под `runc`, ещё жёстче, чем спайк предполагал:
  `--security-opt seccomp=unconfined --security-opt apparmor=unconfined`
  снимает блокировку на создание namespace, но следующий шаг
  (`bwrap --proc /proc`) всё равно падает `Operation not permitted`;
  воспроизводится сквозным успехом только под `--privileged`. Не файл
  Dockerfile/Makefile — `docker run`/`docker-compose.yml` флаги вне
  файлового скоупа T3 (`security_opt`/`cap_add` — предмет compose-блока T1,
  design-brief § Executor уже фиксирует `runtime: runsc` для прод-топологии,
  под которым синтаксис syscall-фильтрации иной — не проверялось, `runsc` не
  установлен на этом хосте). Эскалируется архитектору/оркестратору, не
  чинится в рамках файлового скоупа T3.6.

- **T3.7: `--security-opt` вместо `--privileged` — применённое решение
  архитектора, эмпирически подтверждено.** Продолжение находки T3.6 выше.
  Эскалация 2026-08-11 закрыла вопрос: `docker run` для `smoke-executor`
  несёт три флага — `--security-opt seccomp=unconfined --security-opt
  apparmor=unconfined --security-opt systempaths=unconfined` — не
  `--privileged`. Обоснование архитектора: граница изоляции —
  gVisor (прод) + bwrap на джобу, не seccomp-профиль контейнера executor'а
  сам по себе; `--privileged` расширял бы привилегии сверх необходимого и
  давал бы ложное чувство, что контейнерный seccomp — часть периметра
  безопасности джобы, тогда как он им не является (design-brief § Executor:
  граница проходит по видимости ФС через bwrap, не по фильтрации syscall'ов
  контейнера). Проверено этим агентом на том же dev-хосте (Docker CE
  29.6.1, `runc`, дефолтный `builtin` seccomp) заново, третьим независимым
  прогоном после T3.6: с тремя флагами (без `--privileged`) `docker run
  --rm --runtime=runc <три флага> ... learnflow-executor:local
  /app/services/executor/smoke/run_all.sh` проходит `smoke_sandbox.py`
  целиком — `unshare -U --map-current-user -n bwrap ...` создаёт userns и
  монтирует `/proc` без `Operation not permitted`, все четыре внутренние
  проверки (свой workspace, ENOENT на чужом пути, EROFS на `/skills`,
  недостижимая сеть) зелёные. Расхождение с T3.6 (там та же комбинация
  флагов падала на `mount proc`) не разбиралось отдельно — не входит в
  скоуп T3.7 переисследование T3.6-находки, эскалация архитектора уже
  назвала рабочую конфигурацию, эта фаза её применила и подтвердила
  работающей на смоук-пути; add-on Docker CE/kernel могли обновиться между
  прогонами T3.6 и T3.7 на одном и том же dev-хосте (сессии разнесены по
  времени, версия демона не зафиксирована в T3.6 summary с точностью до
  патч-уровня).
- **T3.7: `docxcompose`/`pandas` — точечный `# type: ignore[import-untyped]`
  в двух смоук-файлах, не запись в корневой `pyproject.toml`.** Оба пакета
  не несут `py.typed`/опубликованных стабов — тот же класс проблемы, что у
  существующих `[[tool.mypy.overrides]]` для `pdfkit`/`mdx_math`/
  `fuzzysearch` в корневом `pyproject.toml`. Инструкция T3.7 ограничивает
  файловый скоуп фазы `services/executor/** + Makefile`; централизованная
  запись в overrides потребовала бы правки корневого `pyproject.toml`, вне
  этого скоупа. Выбран локальный `# type: ignore[import-untyped]` с
  комментарием, объясняющим причину и явно называющим альтернативу —
  осознанное отступление от сложившегося в репозитории паттерна
  (централизованный реестр в одном месте лучше точечных игноров), сделанное
  ради соблюдения более жёсткой границы этой фазы. Кандидат в Follow-ups:
  архитектору решить, стоит ли консолидировать эти две записи в корневой
  `pyproject.toml` следующим точечным изменением (тогда локальные
  `# type: ignore` в `smoke_matplotlib_png.py`/`smoke_python_docx.py`
  убираются).
- **T3.7: очистка tmp-workspace после `smoke-executor` — находка вне
  дословного текста плана.** Первая версия цели делала `rm -rf "$$tmpdir"`
  сразу после прогона; поскольку prep-шаг chown'ит `<tmp>/smoke` на uid
  10001 (требование gVisor к владельцу workspace, находка 4 спайка), `rm`
  от хостового пользователя (uid 1000 на этой машине) падает `Operation not
  permitted` на файлах/каталогах, созданных джобой изнутри песочницы под
  10001 — воспроизведено дважды при первых прогонах цели (осиротевшие
  `/tmp/tmp.*`, не удалявшиеся без `sudo`). Исправлено на месте: перед
  `rm -rf` цель делает симметричный `docker run --user 0 ... chown -R
  $$(id -u):$$(id -g) /workspaces`, возвращая права хостовому пользователю.
  Не меняет семантику теста (chown происходит после того, как результат
  прогона уже зафиксирован в `$$ec`), только гигиену `/tmp`.
- **T3.7: `run_all.sh` не останавливается на первом провале.** Формулировка
  плана («агрегированный итог, ненулевой exit при первом провале») читается
  двояко — как «стоп на первом фейле» или как «после агрегации всех
  результатов — ненулевой exit, если где-то был провал». Выбрано второе:
  скрипт гоняет все шесть сценариев независимо от промежуточных исходов и
  печатает сводку (`run_all: N/6 scenario(s) failed`), что даёт больше
  диагностики за один прогон (например, недостающая транзитивная
  зависимость **и** сломанный шрифтовый пакет видны в одном выводе, а не
  по одному за перезапуск) — тот же принцип, что у `pytest`/CI-раннеров по
  умолчанию. Негативная проверка ворот (Verification) не различает эти два
  прочтения — оба дают ненулевой exit при провале одного сценария, что и
  было проверено.
- **GREEN (R9): ожидание пайпов ограничено грейсом, а не бесконечное.**
  `run_job` дожидался ридеров через голый `join()` — корректно только под
  песочницей, где коллапс pid-namespace гарантирует, что ни один потомок не
  переживёт джобу с открытым концом пайпа. На dev-escape-hatch
  (`sandbox_enabled=False`) pid-ns нет, и процесс, ушедший из группы
  (`setsid … &`), переживает `killpg` и держит пайп открытым — запрос висел
  бесконечно, дедлайн переставал что-либо значить. Из двух предложенных
  вариантов (ограничить ожидание либо просто задокументировать ограничение)
  выбран первый: документация не убирает подвисший навсегда запрос, а
  ограничение ожидания — ровно тот же приём, что уже применён к самой
  джобе (дедлайн + грейс), и переиспользует существующий knob
  `kill_grace_seconds` вместо новой env-переменной. Реализация — `_drain()`:
  общий на оба потока дедлайн `kill_grace_seconds` после смерти обёртки;
  если ридер не дошёл до EOF, джоба всё равно отдаёт результат с тем, что
  успели прочитать. Деградация не молчаливая — маркер в `stderr` (тем же
  каналом, что и усечение вывода: поля `JobResponse` фиксированы
  межтрековым контрактом, отдельного флага в них нет), поле
  `output_incomplete` в логе `job finished` и уровень WARNING вместо INFO
  (§ Logging: «справились, но что-то было не так»). Два побочных изменения
  внутри `_PipeReader`, оба вынужденные: (1) буфер под `threading.Lock` —
  теперь его читают, пока поток пишет, а `bytearray` нельзя одновременно
  декодировать и дописывать; (2) чтение через `os.read(fd, …)` вместо
  буферизованного `pipe.read(n)` — последний блокируется до полного чанка в
  64 KiB, так что при отказе от пайпа всё непрочитанное осталось бы
  невидимым внутри буфера Python, а не в результате. Оба варианта
  возвращают пусто только на EOF, нормальный путь не меняется. Проверено
  эмпирически (`bash -c "echo early; setsid bash -c 'sleep 30' & sleep 0.1"`,
  `timeout=1`, `kill_grace_seconds=2`): раньше — зависание на 30 с, теперь
  возврат за ≈2.1 с с `stdout="early\n"`, маркером в `stderr` и
  `output_incomplete=True` в логе. Автотеста нет намеренно — падающий кейс
  сам подвесил бы прогон (см. R9 в `test-cases.md`). Плата за фикс:
  осиротевший daemon-поток и открытый fd на такой джобе до смерти
  зацепившегося процесса — на боевом (сандбоксированном) пути недостижимо.
- **GREEN (R10): `proc.wait()` в ветке `ProcessLookupError`.** Выход из
  `_kill_process_group` без реапа оставлял `proc.returncode is None` →
  `JobResult.exit_code=None` → 500 на валидации `JobResponse`. Ревьюер
  подтвердил недостижимость (незажатый прямой потомок остаётся зомби, а
  `getpgid`/`killpg` на зомби отрабатывают штатно, так что ESRCH тут не
  возникает), но фикс — одна строка, дешевле, чем держать в контракте
  теоретическую дырку. Зависнуть `wait()` здесь не может: ProcessLookupError
  означает, что pid не существует вовсе, а если бы потомка кто-то уже
  пожал, `subprocess` штатно перехватывает `ChildProcessError` и ставит
  `returncode=0`.
- **GREEN (R11): `tini` как ENTRYPOINT образа — init-процесс, жнущий сирот.**
  Каждая джоба оставляла в контейнере зомби `bwrap` (`State: Z`, `PPid: 1`),
  накопление ровно 1:1 с числом джоб и независимо от их исхода — вскрыто
  ручным прогоном `{T3.7}` (наблюдение за таблицей процессов, вне ассерта
  кейса). Первопричина не в runner'е: `killpg` отрабатывает штатно, но
  bwrap-потомок переживает свою обёртку и реперентится на PID 1 контейнера, а
  PID 1 здесь — `uvicorn` из `CMD`, обычный процесс без reaping-цикла, так что
  запись в таблице процессов остаётся навсегда. Под `pids_limit: 256`
  прод-топологии это медленная утечка PID-слотов: после N джоб контейнер
  перестаёт форкать, а рестарт маскирует симптом — отсюда severity major, хотя
  сам сервис отвечает корректно. Из двух мест, где чинится (`init: true` в
  compose-блоке executor'а — T1, либо init в образе), решением архитектора
  выбрано второе: `ENTRYPOINT ["tini", "--"]` плюс пакет `tini` в apt-слое.
  Обоснование — гарантия должна держаться везде, где запускается образ (смоук,
  ручной `docker run`, будущий compose, прод), а не только там, где не забыли
  флаг; compose и Makefile этим фиксом не тронуты. `tini` пробрасывает сигналы
  в CMD-процесс без изменений, поэтому kill-контракт джобы (`start_new_session`
  + `killpg` + `--die-with-parent` + коллапс pid-ns) остаётся ровно прежним, а
  `stop_grace_period` executor-контейнера продолжает работать как раньше.
  Верифицировано по первопричине на пересобранном образе: шесть джоб (три
  успешных, два таймаута, одна `code` с трейсбеком) → в `/proc` ноль записей со
  `State: Z`, `PID 1` — `tini`, `uvicorn` его прямой потомок (до фикса тот же
  прогон на четырёх джобах давал четыре зомби `bwrap` с `PPid: 1`);
  `docker stop` — graceful shutdown uvicorn за 0.84 с и exit 143 (SIGTERM
  доехал через tini); `make smoke-executor` — все шесть сценариев зелёные;
  executor-строка `make test` — 87 passed.

- **F8 (нит B, code review) — `pillow`/`lxml` были только транзитивными зависимостями, хотя `system.txt` обещает их напрямую.** Добавлены явно в `services/executor/pyproject.toml` (`pillow>=12.3.0`, `lxml>=6.1.1` — версии уже разрешённые в `uv.lock`); один прогон `uv lock` + `uv sync --all-packages`, diff `uv.lock` ограничен ровно этими двумя записями зависимостей `executor`. `services/executor` — 87 passed.

## Follow-ups

- `backend/tests/agent/test_pricing_external.py::test_active_model_prices_within_drift_tolerance`
  красный на прогоне `make test` этой фазы: live-цены нескольких моделей (`deepseek-v4-flash`,
  `deepseek-v4-pro`, `glm-5.2`) разошлись с `pricing.yaml` на 14.6–93.2% при допуске 10%.
  Тест помечен `@pytest.mark.external` (хит внешнего API), файл — вне файлового скоупа
  трека T3 (`backend/**` принадлежит T1). Не связано с изменениями T3.1 (executor/Makefile/
  root pyproject/uv.lock); похоже на рыночный дрейф цен провайдеров либо на то, что
  `test`-цель Makefile не исключает `external`-маркер по умолчанию. Кандидат на внимание
  архитектора/T1 — вне полномочий эскалации этой фазы (файл не в scope T3).
- ~~`backend/app/storage/workspace.py` не проходит `ruff format --check .`~~ — устарело.
  Находка T3.3 (файл вне скоупа T3, не трогался в этой фазе); на прогоне `make check`
  в T3.4 (полный репозиторный прогон) `ruff format --check .` зелёный на 357 файлах,
  `backend/app/storage/workspace.py` в их числе. Похоже, файл отформатирован в рамках
  параллельного трека T1/T2 между сведением T3.3 и T3.4. Весь `make check` (ruff check,
  ruff format --check, mypy backend/siem/executor/tools, `lint-imports` 9/9,
  `arch_checker`) зелёный по всему репозиторию на момент сдачи T3.4.
- **T3.5: полный репозиторный `make check` флапал во время сдачи фазы** — два
  последовательных прогона упали на двух разных, не связанных друг с другом
  файлах `backend/**` (`ruff format` на `image_generation.py`, затем `ruff
  check F821` на `chat.py`, обе ошибки исчезали/менялись между запусками) —
  однозначный признак параллельного незакоммиченного трека, пишущего в те же
  файлы `backend/**` во время прогона (тот же паттерн, что и предыдущая
  находка про `workspace.py`, но live, не post-hoc). Изолированный прогон
  `ruff check`/`ruff format --check`/`mypy` строго по `services/executor/`
  зелёный без замечаний — файлы T3.5 (`schemas.py`, `routes.py`, `main.py`,
  `sandbox.py`, `runner.py`, `logging.py`) сами по себе гейт проходят;
  нестабильность — не в них. Не эскалировалось отдельным стопом (см. отчёт
  агента) — задокументировано здесь по тому же принципу, что и предыдущая
  находка о параллельных изменениях.
- ~~**T3.6: dev-хост верификации требует `--privileged` для сквозного `bwrap`
  внутри Docker-контейнера.**~~ — **закрыто в T3.7.** Эскалация архитектора
  2026-08-11: `--security-opt seccomp=unconfined --security-opt
  apparmor=unconfined --security-opt systempaths=unconfined` (без
  `--privileged`) — рабочая конфигурация, `smoke-executor` несёт эти три
  флага. Проверено этим агентом на том же dev-хосте — `smoke_sandbox.py`
  (полный `unshare`+`bwrap`-префикс) под `RUNTIME=runc` с этими тремя
  флагами зелёный без `--privileged`; T3.6-находка о падении на `mount
  proc` с той же комбинацией флагов не переисследовалась (вне скоупа этой
  фазы) — подробности и гипотеза расхождения см. «Решения и обоснования».
  `docker-compose.yml`-эквивалент (`security_opt`/`cap_add` для сервиса
  `executor`, T1) — за пределами файлового скоупа T3, но теперь имеет
  проверенную рабочую формулировку для переноса.
- **T3.7: локальные `# type: ignore[import-untyped]` для `docxcompose`/
  `pandas` в смоук-файлах — кандидат на консолидацию в корневой
  `[[tool.mypy.overrides]]`.** Оба пакета не несут стабов, тот же класс
  проблемы, что у существующих записей для `pdfkit`/`mdx_math`/
  `fuzzysearch`; T3.7 не тронула корневой `pyproject.toml` (вне файлового
  скоупа фазы) и оставила точечные игноры в
  `services/executor/smoke/smoke_matplotlib_png.py` и
  `smoke_python_docx.py`. Архитектору — решить, стоит ли отдельным точечным
  изменением унифицировать со сложившимся в репозитории паттерном.

## SOFA-посты (id / применил / результат)
