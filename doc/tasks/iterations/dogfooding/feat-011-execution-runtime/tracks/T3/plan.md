# Implementation Plan: feat-011 / трек T3 — Executor-сервис

## Контекст

Трек поднимает третий standalone-сервис репозитория — `services/executor/`: тупой исполнитель джоб, единственное место, где запускается недоверенный код. Он принимает `POST /jobs {project_id, code|cmd, timeout}`, синхронно исполняет команду под deadline внутри bwrap-песочницы с пустым netns и возвращает `{stdout, stderr, exit_code}`. Продуктовой логики, auth, знания о пользователях и отчёта о файлах у него нет — всё это остаётся в backend (T1).

Источники (не пересказываются здесь, читаются реализующим агентом):

- [design-brief.md](../../design-brief.md) — § Executor: контракт джобы, § Конвенции, § Безопасность, § Партиция треков (границы T3, политика `uv.lock`, межтрековые контракты 2, 4–7)
- [ADR-031](../../../../../../tech/adr/ADR-031-execution-runtime-isolation.md) — решение об изоляции, следствия спайка
- [spikes/spike-bwrap-gvisor.md](../../spikes/spike-bwrap-gvisor.md) — рабочий bwrap-префикс (вариант A), ловушка владельца workspace, ограничения переноса на прод
- [acceptance.md](../../acceptance.md) — блок B (B1–B9), B4 — опора для смоук-набора
- [conventions.md](../../../../../../tech/conventions.md) — § Структура проекта → Dockerfile, § Секреты и fail-fast, § Обработка ошибок, § Что попадает в env, § Logging, § Makefile
- Референс: `services/siem-service/` (pyproject, Dockerfile, Settings с префиксом, `/health`, раскладка по слоям)

**Файловый скоуп трека:** `services/executor/**`, `Makefile`, корневой `pyproject.toml`, `uv.lock`. `docker-compose.yml`, `.env*.example`, `backend/**` — чужие (T1); нужен чужой файл → эскалация оркестратору.

**Тесты пишет `test-author`** в `services/executor/tests/` после трековых фаз — фазы ниже тестов не содержат, но каждая несёт исполняемую verification.

### Решения, принятые планом (следуют из брифа/конвенций, не новая архитектура)

- **Имена.** Дистрибутив и python-пакет — `executor` (по образцу `siem-service`: имя дистрибутива = имя директории), модуль `services/executor/executor/`. Порт — `8002` (8000 — app, 8001 — siem).
- **Тулчейн джобы — зависимости пакета `executor`.** numpy/pandas/matplotlib/python-docx/docxcompose/pypdf едут в `[project.dependencies]`, а не отдельной группой: только так они попадают в `uv.lock` и в образ через шаблонный `uv sync --locked --no-dev --package executor` (§ Dockerfile). Системная часть (pandoc, шрифты, bubblewrap, curl) — apt-слоем.
- **Состав образа v1 = то, что покрывает смоук** (matplotlib, pandas/numpy, pandoc, python-docx + docxcompose, извлечение текста из pdf, шрифты с кириллицей). Node/Chromium/marp в v1 не запекаются — их состав финализируют спайки feat-005/006 (бриф § Executor), добавление = релиз образа.
- **Mount-набор песочницы — в коде, не в env.** Это инвариант безопасности (§ Что попадает в env: бизнес-инвариант → код). В env уходят только операционные ручки (корни, таймауты, потолок вывода, kill-grace, уровень лога).
- **Обработчик `/jobs` — синхронный `def`** (FastAPI уводит его в threadpool, [conventions/api.md](../../../../../../tech/conventions/api.md) § Блокирующий код): джоба синхронна by design, весь код исполнения — блокирующий `subprocess` + чтение пайпов. Следствие — параллелизм джоб ограничен размером threadpool Starlette (по умолчанию 40); при текущем масштабе это выше, чем потолки CPU контейнера, и отдельной очереди бриф не вводит.

## Фазы

### T3.1: Пакет `services/executor/`, регистрация в workspace, гейты Makefile

**Цель:** завести пустой, но валидный workspace-член `executor` и один раз перегенерировать `uv.lock` (политика «один писатель», бриф § Партиция треков).

**Изменения:**

- `services/executor/pyproject.toml` — по образцу `services/siem-service/pyproject.toml`: `name = "executor"`, `requires-python = ">=3.12"`; runtime-зависимости сервиса (`fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `structlog`) и тулчейн джобы (`numpy`, `pandas`, `matplotlib`, `python-docx`, `docxcompose`, `pypdf`); `[tool.setuptools.packages.find] include = ["executor*"]`; `[tool.pytest.ini_options]` (`testpaths = ["tests"]`, маркеры `unit`/`integration`/`slow` — как у siem); `[dependency-groups] dev = ["learnflow-testing", "pytest-xdist>=3.6"]` + `[tool.uv.sources] learnflow-testing = { workspace = true }`.
- `services/executor/executor/__init__.py` — пустой пакет-маркер.
- `services/executor/tests/__init__.py` — плейсхолдер, чтобы `make test` не падал на несуществующем пути (pytest exit 4); содержимое пишет `test-author`.
- Корневой `pyproject.toml` — `services/executor` в `[tool.uv.workspace] members` (алфавитно, перед `services/siem-service`). Контракты import-linter для executor **не заводятся** — покрытие arch-checker'ом вне итерации (бриф § Вне партиции).
- `uv.lock` — **единственный за трек** прогон `uv lock`.
- `Makefile` — `uv run mypy services/executor/` в целях `type-check` и `check` (отдельной строкой: у executor свой top-level пакет `tests`, mypy не терпит два одноимённых модуля в одном прогоне); строка прогона pytest executor'а в `test` и `test-parallel` по шаблону siem (`uv run --package executor pytest -c services/executor/pyproject.toml --rootdir services/executor services/executor/tests`, толерантность к exit 5).

**Verification:**

- `uv lock --check` — lock согласован с манифестами.
- `uv sync --package executor` проходит; `uv run --package executor python -c "import numpy, pandas, matplotlib, docx, docxcompose, pypdf"` — тулчейн резолвится.
- `make check` зелёный (ruff + mypy по новому корню + arch-check).
- `make test` зелёный (executor-строка отрабатывает на пустом каталоге тестов через exit 5).
- `git diff --stat` показывает ровно один изменённый `uv.lock`.

### T3.2: Settings, приложение, `/health`

**Цель:** поднять минимальное FastAPI-приложение executor'а с `EXECUTOR_`-конфигурацией и healthcheck-эндпоинтом.

**Изменения:**

- `services/executor/executor/config.py` — `Settings(BaseSettings)` с `env_prefix="EXECUTOR_"`; поля и дефолты — точно по секции «EXECUTOR_-knobs» ниже. Секретов у сервиса нет, обязательных полей нет (§ Секреты и fail-fast к нему не применяется — доступ контролирует exec-сеть, бриф § Executor).
- `services/executor/executor/logging.py` (или inline в `main.py`, если укладывается в несколько строк) — минимальная настройка structlog по `settings.log_level` (`structlog.make_filtering_bound_logger`). Стиль логов — keyword-args (§ Logging).
- `services/executor/executor/main.py` — `create_app()`: `Settings()` в `create_app`, кладётся в `app.state.settings`; `GET /health → {"status": "ok"}`; `app = create_app()` на модульном уровне (как у siem). Module-level синглтонов нет (жёсткое правило).
- `services/executor/executor/api/deps.py` — тонкий `SettingsDep` через `request.app.state` (по конвенции lifespan → app.state → Depends).

**Verification:**

- `uv run --package executor python -c "from executor.main import create_app; print(sorted(r.path for r in create_app().routes))"` — виден `/health`.
- Локальный запуск `uv run --package executor uvicorn executor.main:app --port 8002 --app-dir services/executor` + `curl -s localhost:8002/health` → `{"status":"ok"}`.
- `EXECUTOR_MAX_TIMEOUT_SECONDS=42 uv run --package executor python -c "from executor.config import Settings; print(Settings().max_timeout_seconds)"` → `42` (префикс читается).
- `make check` зелёный.

### T3.3: Sandbox-префикс: построение argv и env джобы

**Цель:** чистая функция, собирающая полный argv джобы (`unshare … bwrap … -- <команда>`) и её scrubbed env — без запуска процессов.

**Изменения:**

- `services/executor/executor/sandbox.py`:
  - `build_job_argv(workspace: Path, command: list[str], settings) -> list[str]` — префикс варианта A из спайка: внешняя обёртка `unshare -U --map-current-user -n` (родной `--unshare-net` bwrap под gVisor фатален), затем `bwrap` с обязательными флагами kill-контракта `--unshare-pid --die-with-parent --new-session` плюс `--unshare-user --unshare-ipc --unshare-uts`, `--clearenv`, `--setenv` минимального набора, `--ro-bind /usr`, симлинки merged-usr (`/bin`, `/lib`, `/lib64`, `/sbin`), **суженный** ro-bind `/etc` (по спайку: `ld.so.cache`, `passwd`, `group`, `resolv.conf` не нужен без сети, `ssl/certs`, `/etc/fonts` для fontconfig — точный список подтверждается смоуком T3.7), `--ro-bind` префикса venv (берётся из `sys.prefix`, не хардкодится), `--proc /proc --dev /dev --tmpfs /tmp`, `--bind <workspace> /workspace`, `--ro-bind <skills_root> /skills`, `--chdir /workspace`, `--` + команда.
  - env джобы: `PATH = {sys.prefix}/bin:/usr/local/bin:/usr/bin:/bin`, `HOME=/workspace`, `LANG=C.UTF-8`, `MPLCONFIGDIR=/tmp/mpl`, `XDG_CACHE_HOME=/tmp/cache` (matplotlib и fontconfig пишут кэш — иначе шум/падения на ro-корне); env executor-процесса не наследуется (`--clearenv` + `env={}` у Popen).
  - `settings.sandbox_enabled = False` (dev-путь без bwrap) возвращает голую команду и пишет `logger.warning` со `sandbox_enabled=False` — молчаливой деградации нет (§ Восстановление).
  - Резолв workspace: `resolve_workspace(project_id)` — `project_id` обязан быть одним безопасным сегментом (`^[A-Za-z0-9._-]{1,128}$`, не `.`/`..`), путь резолвится и проверяется `is_relative_to(workspaces_root)`. Executor остаётся тупым, но не усиливает traversal; несоответствие → доменное исключение слоя (не `HTTPException`, § Модель ошибок).
  - Директорий executor **не создаёт** (бриф § Executor: все mkdir у backend) — отсутствующий workspace = ошибка запроса.
- `services/executor/executor/exceptions.py` — узкие доменные исключения (`InvalidProjectIdError`, `WorkspaceMissingError`), наследуют `Exception` (внутренние исключения подсистемы, гасятся на барьере роутера — § Модель ошибок, случай 2).

**Verification:**

- Ручной прогон собранного argv на хосте (bwrap 0.11 присутствует — среда спайка): временный каталог `wsA` с маркером, соседний `wsB`; `python -c` внутри песочницы читает свой файл (OK), `wsB` даёт `ENOENT`, запись в `/skills` — `EROFS`, `socket.socket()` — `EAFNOSUPPORT` (пустой netns). Ровно матрица C1/C2/G4 спайка на хосте.
- `uv run --package executor python -c "…build_job_argv…"` печатает argv; глазами сверить с вариантом A спайка (все три флага kill-контракта на месте).
- Негативные кейсы резолва: `project_id="../etc"`, `"a/b"`, `""` → исключение.
- `make check` зелёный.

### T3.4: Job runner — deadline, kill-цепочка, потолок вывода

**Цель:** синхронный запуск подготовленного argv с жёстким deadline, гарантированным убийством потомков и ограниченным по объёму выводом.

**Изменения:**

- `services/executor/executor/runner.py`:
  - `run_job(workspace, command, timeout, settings) -> JobResult(stdout, stderr, exit_code, timed_out)`.
  - `subprocess.Popen(argv, start_new_session=True, env=job_env, stdout=PIPE, stderr=PIPE, cwd=…)` — `start_new_session` обязателен: deadline бьёт `os.killpg(os.getpgid(proc.pid), SIGTERM)` по группе **обёртки**, дальше `--die-with-parent` уносит джобу, коллапс pid-ns (`--unshare-pid`) добивает внуков (три звена kill-контракта, бриф § Executor).
  - Эскалация: `SIGTERM` → ожидание `kill_grace_seconds` → `SIGKILL` по той же группе; `proc.wait()` после.
  - Потолок вывода: **не** `communicate()` (он буферизует неограниченно → OOM сервиса, ровно тот сценарий, ради которого knob вводится). Два reader-потока читают пайпы чанками, удерживают первые `max_output_bytes` на поток, остальное вычитывают и выбрасывают (иначе джоба виснет на полном пайпе до deadline); при усечении к тексту дописывается явная пометка вида `…[output truncated: N bytes dropped]`.
  - Таймаут — не исключение наружу: результат несёт `exit_code = -SIGKILL/-SIGTERM` (или отдельный признак `timed_out`) и диагностику в `stderr`; трактовка «ошибка джобы = обычный результат» живёт в backend, executor просто честно отдаёт исход.
  - Декодирование — `utf-8` с `errors="replace"` (недоверенный вывод не должен ронять сервис).
  - Логи: `logger.info("job finished", project_id=…, exit_code=…, duration_ms=…, timed_out=…, stdout_truncated=…)`; уровень WARNING на таймаут, ERROR — только на инфраструктурный отказ запуска (§ Logging).

**Verification (на хосте, через `uv run --package executor python -c …`):**

- Нормальный прогон: `echo hello` → `exit_code=0`, `stdout="hello\n"`.
- Deadline: `sleep 300` с `timeout=2` → возврат ≈2 с, `timed_out=True`; `pgrep -f "sleep 300"` пуст.
- Внуки: команда `bash -c 'sleep 300 & sleep 300'` с `timeout=2` → после возврата ни одного живого `sleep` (проверка коллапса pid-ns).
- Потолок вывода: `python -c "print('x'*10_000_000)"` при `max_output_bytes=1024` → длина stdout ≈1 KiB + пометка, RSS процесса не растёт (наблюдать `ps -o rss`), команда завершается штатно, а не виснет.
- Ненулевой код: `sh -c 'echo err >&2; exit 3'` → `exit_code=3`, stderr доехал.
- `make check` зелёный.

### T3.5: `POST /jobs` — схемы, роутер, обработка отказов

**Цель:** замкнуть зафиксированный партицией HTTP-контракт поверх runner'а.

**Изменения:**

- `services/executor/executor/api/schemas.py` — `JobRequest` (`project_id: str`, `code: str | None`, `cmd: str | None`, `timeout: float | None`) с валидатором «ровно одно из `code`/`cmd`» (валидация схемой, не `if` в handler'е — [conventions/api.md](../../../../../../tech/conventions/api.md) § Status codes); `JobResponse` (`stdout: str`, `stderr: str`, `exit_code: int`) — **поля ответа менять нельзя** (межтрековый контракт 2).
- `services/executor/executor/api/routes.py` — `POST /jobs`, синхронный `def`-handler:
  - клампит `timeout` в `[0, max_timeout_seconds]`, дефолт `default_timeout_seconds` при `None`; срабатывание клампа — `logger.warning` (защитный потолок, не второй источник правды: T1 обязан держать backend-deadline ≤ `EXECUTOR_MAX_TIMEOUT_SECONDS`, см. § knobs);
  - `cmd` → команда `["bash", "-c", cmd]` (**не** `-lc`: логин-шелл источает `/etc/profile`, который на Debian переписывает собранный PATH джобы — инвариант scrubbed env держался бы случайно);
  - `code` → исходник кладётся во временный файл **вне workspace** и ro-биндится в песочницу фиксированным путём (`--ro-bind <tmp> /tmp/job.py`, запуск `python /tmp/job.py`); ro-bind вставляется в argv **строго после** `--tmpfs /tmp` (bwrap применяет операции по порядку — иначе tmpfs замаскирует файл и ветка молча сломается): workspace остаётся чистым, трейсбек читаем, файл удаляется в `finally`. По резолюции OQ-1 основная ветка T1 — `cmd`, `code` — реализованный резерв;
  - результат runner'а → `JobResponse`;
  - отказы резолва/отсутствующего workspace → 400/404 (единый handler на барьере, не `raise HTTPException` из доменного слоя).
- `services/executor/executor/main.py` — подключение роутера, регистрация exception-handler'а для доменных исключений слоя.

**Verification:**

- Локальный uvicorn (порт 8002) + временный `EXECUTOR_WORKSPACES_ROOT` с каталогом `p1`:
  - `curl -X POST … -d '{"project_id":"p1","cmd":"echo hi"}'` → `{"stdout":"hi\n","stderr":"","exit_code":0}`;
  - `{"code":"import sys; print(sys.version)"}` → версия Python в stdout;
  - `{"project_id":"p1","cmd":"sleep 300","timeout":2}` → ответ ≈2 с с диагностикой таймаута, HTTP 200;
  - `{"project_id":"../etc","cmd":"id"}` и `{"project_id":"nope","cmd":"id"}` → 4xx, не 500;
  - и `code`, и `cmd` разом / ни одного → 422.
- Джоба не видит env сервиса: `EXECUTOR_MAX_OUTPUT_BYTES=…` в окружении uvicorn, `{"cmd":"env"}` → в выводе только PATH/HOME/LANG/MPL*/XDG* (проверка B1 на уровне процесса).
- `make check` зелёный.

### T3.6: Dockerfile — толстый образ, non-root uid 10001

**Цель:** воспроизводимый образ executor'а со всем запечённым тулчейном, bwrap и non-root пользователем.

**Изменения:**

- `services/executor/Dockerfile` (build context — корень репо, § Dockerfile):
  - база `python:3.12-slim-bookworm`, `COPY --from=ghcr.io/astral-sh/uv:0.11.21` (тот же pin, что в двух существующих Dockerfile);
  - apt-слой: `bubblewrap`, `util-linux` (даёт `unshare`), `pandoc`, `curl` (для compose-healthcheck), шрифты с кириллицей и математикой (`fonts-dejavu`, `fonts-liberation2`, `fonts-noto-core`), `ca-certificates`; `rm -rf /var/lib/apt/lists/*`;
  - два `uv sync` по шаблону siem — оба с `--locked --no-dev --package executor`, первый с bind-mount'ами манифестов **всех** workspace-членов (включая `services/executor/pyproject.toml`) и `--no-install-workspace`;
  - набор `COPY` — **1:1 из `services/siem-service/Dockerfile`** (корневые `pyproject.toml`+`uv.lock`, `packages/`, манифесты `backend/` и `tools/*`, `services/`): второй `uv sync --locked` идёт по содержимому образа и падает на резолве, если манифест любого workspace-члена отсутствует на диске; вместе с `services/` приезжает `smoke/` (нужен make-цели T3.7);
  - non-root: `useradd -u 10001 -m -d /home/executor executor` (uid 10001 — межтрековый контракт 4), владение `/app/.venv` и рабочих каталогов за ним, `USER 10001`;
  - `ENV PYTHONUNBUFFERED=1`, `PATH=/app/.venv/bin:$PATH`, `EXPOSE 8002`;
  - `CMD ["uvicorn","executor.main:app","--host","0.0.0.0","--port","8002","--app-dir","services/executor"]` — entrypoint-скрипт не нужен (миграций у сервиса нет).
- `Makefile` — цель `docker-build-executor` (`docker build -f services/executor/Dockerfile -t learnflow-executor:local .`): compose трогать нельзя (скоуп T1), а сборка образу нужна уже сейчас (межтрековый контракт 7).

**Verification:**

- `make docker-build-executor` — сборка проходит; `docker run --rm learnflow-executor:local id` → `uid=10001`.
- `docker run --rm learnflow-executor:local sh -c 'bwrap --version; unshare --version; pandoc --version | head -1; fc-list | wc -l'` — всё присутствует.
- `docker run --rm learnflow-executor:local python -c "import numpy, pandas, matplotlib, docx, docxcompose, pypdf; print('ok')"`.
- `docker run --rm learnflow-executor:local pip list 2>/dev/null | grep -c pytest` → `0` (dev-группа не просочилась).
- Проба bwrap от non-root внутри образа: `docker run --rm learnflow-executor:local bwrap --unshare-user --unshare-pid --ro-bind /usr /usr --symlink usr/bin /bin -- /bin/true` → exit 0 (та самая «первая проверка на проде» из спайка, но под runc).

### T3.7: Смоук-набор образа + make-цель с параметром runtime

**Цель:** ворота релиза образа — реальные сценарии тулчейна, прогоняемые внутри собранного образа одной командой, с переключаемым runtime (runc — гейт релиза, runsc — шаг чек-листа деплоя).

**Изменения:**

- `services/executor/smoke/` — сценарии-скрипты (каждый: ненулевой exit при провале, вывод в одну строку `PASS/FAIL <имя>`), покрывают B4 и приёмочные A4/A12/feat-012:
  - `smoke_matplotlib_png.py` — расчёт по pandas/numpy + график → PNG; проверка magic-байтов и ненулевого размера;
  - `smoke_pandoc_docx.sh` — `pandoc md → docx`, проверка ZIP-сигнатуры и обратного чтения через python-docx;
  - `smoke_pdf_text.py` — извлечение текста из фикстуры `smoke/fixtures/sample.pdf` (маленький файл в репозитории — детерминированнее генерации на лету), проверка маркерной строки;
  - `smoke_python_docx.py` — сборка .docx из python-docx + склейка через docxcompose, обратное чтение абзацев;
  - `smoke_fonts.py` — `fc-match` по DejaVu/Noto + рендер кириллического заголовка matplotlib без предупреждений о недостающих глифах;
  - `smoke_sandbox.py` — полный префикс `unshare + bwrap` из `executor.sandbox` внутри образа: запись в свой workspace (проверяет требование «каталог принадлежит uid джобы»), ENOENT на чужой каталог, EROFS на `/skills`, отсутствие сокетов. Под `--runtime=runsc` этот сценарий и есть прод-верификация bwrap из § Конвенции;
  - `run_all.sh` — последовательный прогон, агрегированный итог, ненулевой exit при первом провале.
- `Makefile` — цель `smoke-executor` с параметром: `make smoke-executor [RUNTIME=runc|runsc]` (дефолт `runc`), внутри — `docker run --rm --runtime=$(RUNTIME) -v <tmp workspaces>:/workspaces -v $(PWD)/skills:/skills:ro learnflow-executor:local /app/services/executor/smoke/run_all.sh`; **подготовка workspace-каталога — часть цели**: `<tmp>/workspaces/<project>` должен принадлежать uid 10001 до прогона (chown подготовительным `docker run --user 0 … chown 10001:10001 …` либо эквивалент) — bind-mount хостового tmp сохраняет владельца хоста (uid 1000), и без chown `smoke_sandbox.py` упадёт по правам раньше, чем проверит gVisor-инвариант «каталог принадлежит uid джобы»; зависимость от `docker-build-executor` не зашивать (пересборка — явный шаг), но упомянуть в help-строке.
- Смоук-скрипты линтуются и типизируются наравне с кодом (`make check` их видит) — держать их ruff/mypy-чистыми.

**Verification:**

- `make docker-build-executor && make smoke-executor` → все сценарии PASS, exit 0.
- Негативная проверка ворот: временно сломать один сценарий (или удалить пакет из образа локальным `--build-arg`/ручным `docker run … pip uninstall` в одноразовом контейнере) → цель падает ненулевым кодом. Ворота обязаны ловить недостающую транзитивную зависимость.
- `make smoke-executor RUNTIME=runsc` — на dev-хосте, где runsc не установлен, цель должна падать с внятной ошибкой docker, а не молча уходить на runc (проверить, что параметр реально доезжает).
- `make check` зелёный (смоук-скрипты проходят ruff/mypy).

## EXECUTOR_-knobs (контракт для T1)

Точный список env-переменных executor-сервиса. T1 переносит их в `docker-compose.yml`, `.env.example`, `.env.local.example` (жёсткое правило «4 синхронных места»; четвёртое — `Settings` — у T3).

| Env | Дефолт | Назначение |
|-----|--------|-----------|
| `EXECUTOR_WORKSPACES_ROOT` | `/workspaces` | Корень workspace'ов внутри контейнера; в compose сюда монтируется общий volume (rw) |
| `EXECUTOR_SKILLS_ROOT` | `/skills` | Точка ro-монтирования каталога скиллов репозитория |
| `EXECUTOR_DEFAULT_TIMEOUT_SECONDS` | `60` | Deadline джобы, если запрос не задал `timeout` |
| `EXECUTOR_MAX_TIMEOUT_SECONDS` | `300` | Потолок, до которого клампится `timeout` из запроса. **`stop_grace_period` контейнера ≥ этого значения + `EXECUTOR_KILL_GRACE_SECONDS`** (бриф § Executor → Деплой) |
| `EXECUTOR_MAX_OUTPUT_BYTES` | `262144` | Потолок вывода **на поток** (stdout и stderr отдельно); сверх — усечение с пометкой. Защита от OOM сервиса |
| `EXECUTOR_KILL_GRACE_SECONDS` | `5` | Пауза между SIGTERM и SIGKILL по группе обёртки при deadline |
| `EXECUTOR_LOG_LEVEL` | `info` | Уровень логирования (симметрия с `LOG_LEVEL` backend) |
| `EXECUTOR_SANDBOX_ENABLED` | `true` | Dev-escape hatch: `false` запускает джобу без bwrap (для окружений без userns) и пишет WARNING на каждый запуск. В compose **не выставляется** — см. Open Question 2 |

Сопутствующее для compose-блока (предметная область T3, межтрековый контракт 5):

- порт сервиса — `8002`, наружу не публикуется; healthcheck — `curl -f http://localhost:8002/health`;
- `user: "10001:10001"` (единый uid, контракт 4), `runtime: runsc`, `read_only` образа не включать (bwrap работает поверх обычной rw-корневой ФС контейнера);
- потолки контейнера: `cpus: "2"`, `mem_limit: 2g`, `pids_limit: 256` (fork-bomb, B8) — операционные дефолты догфудинг-масштаба, тюнятся в compose без релиза;
- монтирования: volume workspaces → `/workspaces` (rw), `./skills` → `/skills:ro`;
- сеть — только `exec` (`internal: true`);
- на стороне backend (knobs T1, здесь для полноты цепочки): URL executor'а `http://executor:8002`; **backend-deadline джобы ≤ `EXECUTOR_MAX_TIMEOUT_SECONDS`** (иначе executor молча клампит — см. WARNING в T3.5); client-timeout httpx = deadline + запас, **запас ≥ `EXECUTOR_KILL_GRACE_SECONDS` + люфт** (ответ на таймаут приходит через deadline + kill-grace + wait; при меньшем запасе каждый таймаут джобы прилетал бы агенту как «runtime unavailable»).

Состав образа v1 (резолюция ревью плана): без Node/Chromium/marp — их добавляют спайки feat-005/006 релизом образа (бриф § Executor: «точный состав финализируют спайки»); v1 покрывает ровно смоук-набор.

## Cross-cutting

- `make check` и `make test` зелёные после каждой фазы; финальный прогон обоих — после T3.7.
- `make docker-build-executor && make smoke-executor` зелёные на финальной ревизии трека (ворота релиза образа).
- Одна ревизия `uv.lock` за весь трек (фаза T3.1). Если поздняя фаза потребует новой зависимости — это отдельная эскалация оркестратору, а не второй `uv lock` втихую.
- Границы скоупа соблюдены: диффа в `docker-compose.yml`, `.env*.example`, `backend/**`, `frontend/**` нет (проверить `git status` перед сдачей трека).
- Покрытие executor'а arch-checker'ом (`SOURCE_ROOTS`, import-linter-контракты, зеркало `problem.py`) сознательно не заводится — `tools/**` вне итерации, кандидат в harvest.
- Прод-нюансы переноса (seccomp/AppArmor Ubuntu, netstack, версии bwrap/runsc) — раздел «Ограничения переноса» спайка; в этом треке они закрываются сценарием `smoke_sandbox.py`, гоняемым `RUNTIME=runsc` на VM в чек-листе деплоя (документирование чек-листа — DOC_UPDATE после барьера, не T3).

## Open Questions

Все вопросы закрыты на эскалации 2026-08-11 (оркестратор + архитектор), открытых нет.

1. **Ветка `code` в `POST /jobs`.** **Закрыто (оркестратор):** T1 шлёт `cmd` для `execute_code` (бриф § Контракты файловых инструментов — backend сам пишет исходник во временный файл workspace и адресует относительным путём). Ветка `code` остаётся реализованной резервной частью контракта (через ro-bind `/tmp/job.py`), как в плане.
2. **`EXECUTOR_SANDBOX_ENABLED`.** **Закрыто (архитектор):** оставить — дефолт `true`, WARNING на каждый запуск при выключении, в compose не выставляется вовсе (прецедент наблюдаемой деградации — kill-switch ADR-029).
3. **problem+json для executor.** **Закрыто (оркестратор):** третье зеркало `problem.py` не заводится — дефолтные ответы FastAPI достаточны для внутреннего сервиса с единственным машинным клиентом; уточнение формулировки «оба сервиса» в конвенции — кандидат в Follow-ups (harvest).
4. **Версия pandoc.** **Закрыто (оркестратор):** apt bookworm (2.17) в v1; переход на пинованный 3.x — по требованиям спайков feat-005/006 отдельным релизом образа (бриф: состав финализируют спайки).
