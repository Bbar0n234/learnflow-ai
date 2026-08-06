# Implementation Plan: chore-001 / трек T2 — прод-образы без dev-зависимостей

## Контекст

Трек вычищает два прод-образа: они собираются через `uv sync --locked --all-packages` без `--no-dev`, поэтому тянут dev-группу (`pytest`, `mypy`, `ruff`, `pre-commit`, `learnflow-testing` → `testcontainers` с docker SDK) и всех членов workspace разом — в образ `siem-service` заезжает весь LangChain/LangGraph-стек backend'а, чей код туда даже не копируется. Дизайн-решение и обоснование — [design-brief § 4](../../design-brief.md#4-прод-образы-без-dev-зависимостей); здесь только декомпозиция на фазы.

**Файловый скоуп трека — ровно четыре файла** (см. § Партиция треков брифа): `backend/Dockerfile`, `services/siem-service/Dockerfile`, `backend/entrypoint.sh`, `services/siem-service/entrypoint.sh`. Python-код, `docker-compose.yml`, `.env*`, CI (`ci.yml`) и `doc/tech/conventions.md` — **не трогаем**: строку § Dockerfile про `uv sync --locked --all-packages` правит трек T1, CI осознанно остаётся на `--all-packages` с dev-группой.

**Автотестов у трека нет.** Верификация — `docker build` каждого образа плюс инспекция содержимого через разовые `docker run`. `docker compose up` / `down` **запрещены**: в этом worktree параллельно идёт трек с testcontainers-БД, и остановка стека его уронит. `docker build` и `docker run --rm` состояние compose не трогают.

## Согласованные факты (проверено в этом worktree, uv 0.11.26; образы pinned на `ghcr.io/astral-sh/uv:0.11.21`)

- `--no-dev` (`env: UV_NO_DEV`) выключает группу `dev`; `--package <name>` синкает конкретного члена workspace; `--no-install-workspace` (`env: UV_NO_INSTALL_WORKSPACE`) ставит зависимости, не устанавливая самих членов. Все три флага совместимы: `uv sync --locked --no-dev --no-install-workspace --package siem-service --dry-run` отрабатывает без ошибок.
- **`--package` без `--no-dev` цели не достигает.** Dry-run `uv sync --locked --package learnflow-backend` убирает только корневую dev-группу (`mypy`, `ruff`, `pre-commit`, `import-linter`) — 27 пакетов; `pytest`, `pytest-asyncio`, `pytest-xdist`, `testcontainers`, `factory-boy`, `learnflow-testing` остаются, потому что живут в **собственной** dev-группе пакета (`backend/pyproject.toml:51-56`, `services/siem-service/pyproject.toml:38-42`). С `--no-dev` дельта — 41 пакет.
- **`--no-dev` без `--package` цели не достигает для siem.** `--package siem-service --no-dev` выносит из окружения 108 пакетов, включая `langchain`, `langchain-core`, `langchain-openai`, `langchain-mcp-adapters`, `langgraph*`, `langfuse`, `psycopg*`.
- `uv run` поддерживает `--no-sync` с `env: UV_NO_SYNC` — задокументированный флаг (`uv run --help`), а не недокументированный трюк.
- Рантайм от `--no-dev` не ломается: `alembic` и `uvicorn[standard]` объявлены в `[project.dependencies]` **обоих** пакетов (`backend/pyproject.toml:7,25`, `services/siem-service/pyproject.toml:8,11`).
- **PATH различается между образами.** `services/siem-service/Dockerfile:39` ставит `ENV PATH="/app/.venv/bin:$PATH"`, `backend/Dockerfile` — нет. Поэтому вся инспекция содержимого делается **абсолютным** путём `/app/.venv/bin/python`: `--entrypoint python` в backend-образе возьмёт системный интерпретатор без site-packages venv и «провалит» вообще всё, дав ложноположительный результат.
- **`learnflow-backend` и `siem-service` — virtual-члены workspace, в `.venv` они не попадают никогда.** В `uv.lock` у обоих `source = { virtual = "backend" }` / `{ virtual = "services/siem-service" }`, в их `pyproject.toml` нет `[build-system]`. uv такие пакеты не устанавливает — ни с `--package`, ни без него; рантайм получает их код напрямую с диска через `uv run … --app-dir backend` / `--app-dir services/siem-service` в entrypoint'ах. Практическое следствие для верификации: **`import app` и `import siem_service` через `/app/.venv/bin/python` не работают и работать не должны** — ни как позитивная проверка, ни как негативная. Проверять через интерпретатор можно только установленные дистрибутивы. **Не «чинить» это добавлением `[build-system]` в `backend/pyproject.toml` или `services/siem-service/pyproject.toml`**: оба файла вне скоупа трека, а смена virtual → packaged меняет модель сборки всего workspace.
- **Bind-mount'ы и `COPY` pyproject'ов всех членов workspace остаются на месте** — и в кэш-слое, и в siem-Dockerfile (`COPY backend/pyproject.toml`, комментарий `:29-31`). uv требует, чтобы каждый член, объявленный в `[tool.uv.workspace] members` корневого `pyproject.toml`, существовал на диске, независимо от `--package`. Соблазн «раз ставим один пакет — уберём лишние mount'ы» ломает сборку.
- **Почему правка обязана затрагивать оба вызова.** `uv sync` по умолчанию exact: финальный вызов с `--no-dev --package X` вычистит из `/app/.venv` то, что налил кэш-слой. Но docker-слои кумулятивны — файлы, установленные слоем `:21-30` (backend) / `:12-21` (siem), физически остаются в образе, а финальный слой лишь кладёт поверх whiteout. Итог: размер образа и pull-трафик не уменьшаются, плюс лишнее время сборки. Практическое следствие для верификации: проверка «`import pytest` падает» **не различает** правку одного вызова и правку обоих — как не различает их и суммарный размер образа (whiteout поверх записанных файлов оставит его почти прежним). Дискриминатор — размер конкретного RUN-слоя кэша в `docker history`, он обязателен в каждой фазе. См. Open Questions #2.

---

## Фазы

Две фазы, по одному образу в каждой. Независимы, порядок — T2.1 → T2.2 (backend первым: он же эталон приёмов и формулировок комментария). Каждая фаза = один коммит.

### T2.1: backend-образ — runtime-only окружение

**Цель.** Собрать `backend/Dockerfile` так, чтобы в образе жили только рантайм-зависимости пакета `learnflow-backend`, и запретить `uv run` в entrypoint'е возвращать dev-группу при старте контейнера.

**Изменения.**

`backend/Dockerfile`:

1. Строка `:30` (кэш-слой) — `uv sync --locked --no-install-workspace --all-packages` → `uv sync --locked --no-dev --no-install-workspace --package learnflow-backend`.
2. Строка `:44` (финальный слой, «Install project») — `uv sync --locked --all-packages` → `uv sync --locked --no-dev --package learnflow-backend`.
3. Комментарий над кэш-слоем (заменяет/дополняет существующий `# Install Python dependencies (cached layer)`), фиксирующий осознанное расхождение с CI и парность вызовов. Предлагаемый текст (English — как остальные комментарии в файле):

   ```dockerfile
   # Install Python dependencies (cached layer).
   # Production image: runtime deps of this service only. CI deliberately differs
   # (`uv sync --all-packages` with the dev group — see .github/workflows/ci.yml):
   # there the dev toolchain is the point, here it is dead weight and attack
   # surface. Both `uv sync` invocations below must carry --no-dev --package:
   # what this layer installs stays in the image even if the final sync prunes it.
   ```

4. Ни один `--mount=type=bind` из кэш-слоя не удаляется (см. Согласованные факты), `--mount=type=cache,target=/root/.cache/uv` остаётся в обоих слоях.

`backend/entrypoint.sh`: сразу после `set -e` добавить экспорт с однострочным комментарием:

```bash
# The image ships a runtime-only venv (uv sync --no-dev --package). Without this,
# `uv run` re-syncs the environment on container start and pulls the dev group back.
export UV_NO_SYNC=1
```

Сами команды `uv run` (`alembic … upgrade head`, `uvicorn app.main:app`) не переписываются.

**Verification.**

Baseline снимается **до** правок (одна сборка с текущего состояния файлов), чтобы в summary попала дельта размера:

```bash
docker build -f backend/Dockerfile -t learnflow-backend:t2-before .
docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep learnflow-backend
```

После правок:

```bash
docker build -f backend/Dockerfile -t learnflow-backend:t2-after .
```

1. **Рантайм цел** — команда должна завершиться с кодом 0:

   ```bash
   docker run --rm --entrypoint /app/.venv/bin/python learnflow-backend:t2-after \
     -c "import uvicorn, alembic, fastapi, langgraph, langfuse, psycopg, redis, siem_contracts; print('runtime ok')"
   docker run --rm --entrypoint /app/.venv/bin/alembic learnflow-backend:t2-after --version
   docker run --rm --entrypoint /app/.venv/bin/uvicorn learnflow-backend:t2-after --version
   ```

2. **Dev-зависимостей нет** — каждая команда должна завершиться **ненулевым** кодом (`ModuleNotFoundError`):

   ```bash
   for m in pytest _pytest testcontainers learnflow_testing factory mypy; do
     docker run --rm --entrypoint /app/.venv/bin/python learnflow-backend:t2-after -c "import $m" \
       >/dev/null 2>&1 && echo "FAIL: $m present" || echo "ok: $m absent"
   done
   docker run --rm --entrypoint ls learnflow-backend:t2-after /app/.venv/bin
   # в выводе не должно быть pytest, ruff, mypy, lint-imports, pre-commit
   ```

   Дополнительный сигнал корректной работы `--package`: `asyncpg` (зависимость только siem-service) в backend-образе тоже должен отсутствовать.

3. **Entrypoint не пересинкает окружение.**

   ```bash
   docker run --rm --entrypoint grep learnflow-backend:t2-after -n UV_NO_SYNC /app/entrypoint.sh
   docker run --rm --network none \
     -e DATABASE_URL=postgresql+psycopg://x:x@127.0.0.1:5432/x \
     learnflow-backend:t2-after
   ```

   Ожидание: в выводе есть `Running database migrations...`, дальше контейнер падает на недоступной БД (или на валидации обязательных настроек) — конкретная ошибка неважна. Важно, что **до** неё окружение не пересинкалось.

   Критерий (точная формулировка, чтобы не завалить корректную реализацию): в выводе **нет** строки `Installed N packages` и **нет** имён dev-пакетов (`pytest`, `mypy`, `ruff`, `pre-commit`, `testcontainers`). Строка `Resolved N packages` провалом **не считается**: `UV_NO_SYNC` гасит синк окружения, а не этап валидации lock-файла, и под `--network none` `Resolved` — это ожидаемая офлайн-сверка `uv.lock`, установки за ней не следует. `UV_FROZEN` для подавления этой строки **не добавляем** — это уже сверх брифа.

   Опциональный негативный контроль (доказывает необходимость `UV_NO_SYNC`, требует сети): `docker run --rm --entrypoint uv learnflow-backend:t2-after run python -c "import pytest"` — без `UV_NO_SYNC` uv доставит dev-группу и импорт пройдёт. Контейнер разовый, образ не меняется.

4. **Кэш-слой похудел** — эта проверка отличает правку обоих `uv sync` от правки только финального (см. Согласованные факты).

   Суммарный размер образа сам по себе не дискриминатор: правка одного лишь финального вызова оставит его практически прежним (whiteout поверх уже записанных файлов) и «пройдёт» порог «не вырос». Поэтому смотрим на конкретный слой:

   ```bash
   docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' learnflow-backend:t2-before
   docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' learnflow-backend:t2-after
   ```

   Критерий: размер RUN-слоя, чей `CreatedBy` содержит `uv sync … --no-install-workspace --package …` (в `t2-before` — соответствующий ему слой с `--all-packages`), в `t2-after` **строго меньше**. Если он не изменился — кэш-слой не поправлен.

   Дополнительно снять суммарный размер обоих образов (`docker image ls`) — обе цифры и дельта идут в summary.

5. `git status` показывает изменёнными ровно два файла: `backend/Dockerfile`, `backend/entrypoint.sh`.

---

### T2.2: siem-образ — runtime-only окружение без backend-стека

**Цель.** То же для `services/siem-service/Dockerfile`, плюс убрать из образа весь LangChain/LangGraph/Langfuse/psycopg-стек, который заезжал туда через `--all-packages`.

**Изменения.**

`services/siem-service/Dockerfile`:

1. Строка `:21` (кэш-слой) → `uv sync --locked --no-dev --no-install-workspace --package siem-service`.
2. Строка `:36` (финальный слой) → `uv sync --locked --no-dev --package siem-service`.
3. Комментарий над кэш-слоем — по образцу T2.1 (тот же смысл: расхождение с CI осознанно, оба вызова обязаны нести флаги), с добавкой про `--package`: он же отсекает backend-стек, которого в этом образе быть не должно.
4. `COPY backend/pyproject.toml /app/backend/pyproject.toml` (`:32`) и комментарий `:29-31` — **оставить дословно как есть**: требование workspace-резолвера не снимается флагом `--package`, а формулировка комментария после правки остаётся фактически верной (pyproject копируется без исходников — именно чтобы не тащить код backend'а). Переписывать её не нужно.
5. `ENV PATH="/app/.venv/bin:$PATH"` (`:39`) не трогаем.

`services/siem-service/entrypoint.sh`: `export UV_NO_SYNC=1` после `set -e` с тем же комментарием, что в T2.1. Команды `cd … && uv run --package siem-service alembic upgrade head` и `uv run --package siem-service uvicorn …` не переписываются.

**Verification.**

```bash
docker build -f services/siem-service/Dockerfile -t siem-service:t2-before .   # ДО правок
docker build -f services/siem-service/Dockerfile -t siem-service:t2-after .    # ПОСЛЕ
```

1. **Рантайм цел** (exit 0):

   ```bash
   docker run --rm --entrypoint /app/.venv/bin/python siem-service:t2-after \
     -c "import uvicorn, alembic, asyncpg, sqlalchemy, redis, structlog, jwt, siem_contracts; print('runtime ok')"
   docker run --rm --entrypoint /app/.venv/bin/alembic siem-service:t2-after --version
   ```

   `siem_service` в списке импортов сознательно **отсутствует**: пакет virtual, в `.venv` его нет и с корректной правкой не будет (см. Согласованные факты). Его импорт провалил бы верную реализацию и подтолкнул бы к правке `pyproject.toml` вне скоупа трека. Сам факт, что backend-кода в образе нет, проверяется шагом 2.

2. **Backend-стека и dev-группы нет** — каждая строка должна падать:

   ```bash
   for m in langgraph langchain langchain_core langfuse psycopg pytest testcontainers learnflow_testing; do
     docker run --rm --entrypoint /app/.venv/bin/python siem-service:t2-after -c "import $m" \
       >/dev/null 2>&1 && echo "FAIL: $m present" || echo "ok: $m absent"
   done
   docker run --rm --entrypoint ls siem-service:t2-after /app/.venv/bin
   ```

   Отдельно — что в образ не заехал код backend'а:

   ```bash
   docker run --rm --entrypoint ls siem-service:t2-after /app/backend
   # ожидание: ровно одна строка — pyproject.toml (см. COPY :32)
   ```

   Проверка `import app` здесь бесполезна и в список не входит: `app` — код virtual-члена `learnflow-backend`, он не устанавливается в `.venv` ни до правки, ни после, поэтому даёт «ok: absent» независимо от результата трека.

3. **Entrypoint не пересинкает** — аналогично T2.1:

   ```bash
   docker run --rm --entrypoint grep siem-service:t2-after -n UV_NO_SYNC /app/entrypoint.sh
   docker run --rm --network none \
     -e SIEM_DATABASE_URL=postgresql+asyncpg://x:x@127.0.0.1:5432/x \
     -e SIEM_JWT_SECRET=dummy \
     siem-service:t2-after
   ```

   Ожидание: `Running siem-service database migrations...`, затем падение на БД. Критерий тот же, что в T2.1: нет `Installed N packages` и нет имён dev-пакетов в выводе; `Resolved N packages` под `--network none` — ожидаемая офлайн-валидация lock'а, не провал.

4. **Кэш-слой похудел** — здесь ожидается основная экономия (уходит весь LangChain/LangGraph/Langfuse/psycopg-стек, ~108 пакетов по dry-run), но сверяется она послойно, а не по суммарному размеру:

   ```bash
   docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' siem-service:t2-before
   docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' siem-service:t2-after
   ```

   Критерий: слой с `uv sync … --no-install-workspace --package siem-service` в `t2-after` заметно меньше своего `--all-packages`-предшественника в `t2-before` — порядок ожидаемой разницы задают те самые ~108 пакетов. Совпадение размеров означает, что кэш-слой не поправлен. Суммарные размеры обоих образов и дельта — в summary.

5. `git status`: изменены ровно `services/siem-service/Dockerfile` и `services/siem-service/entrypoint.sh`.

---

## Cross-cutting

**Границы.** Ни одна фаза не трогает python-код, `docker-compose.yml`, `.env*`, `Settings`, CI и документацию. Строка про `uv sync --locked --all-packages` в `doc/tech/conventions.md` § Dockerfile — зона T1 (партиция брифа). Если по ходу выяснится, что нужен чужой файл — в Open Questions, не молча.

**Запрет на compose-lifecycle.** `docker compose up/down/restart/stop` запрещены на всё время трека: параллельный трек держит testcontainers-БД. `docker build -f <dockerfile> -t <tag> .` из корня репо предпочтительнее `docker compose build <service>` ещё и потому, что не переписывает тег образа, которым пользуется compose-стек параллельного трека. Все теги — с суффиксом `t2-before` / `t2-after`.

**Sandbox.** `docker build` исполняет демон вне bash-sandbox, CLI ходит к нему через unix-сокет — сетевой изоляции команд это не касается. `make check` / `make test` треком не задеваются (python-код не меняется), прогонять их для приёмки T2 не требуется.

**Порядок фаз и параллельность.** T2.1 и T2.2 технически независимы (разные файлы, разные образы), но исполняются последовательно: комментарий и формулировки из T2.1 переиспользуются в T2.2. Трек целиком независим от T1/T3; T4 стартует после T2, потому что добавит `ARG`/`ENV VITE_SIEM_ENABLED` в стадию `frontend-build` того же `backend/Dockerfile`.

**Артефакт для summary.** Таблица «образ → размер до → размер после → дельта», отдельной колонкой — размер кэш-слоя `uv sync` до и после (из `docker history`), плюс список пакетов, ушедших из siem-образа (по dry-run: 108). Это единственная количественная приёмка трека — тестов у него нет.

**Риски.**

- В образах pinned uv `0.11.21`, локально проверено на `0.11.26`. Семантика флагов между этими версиями не менялась, но если сборка поведёт себя иначе — фиксировать вывод и эскалировать, не подбирая флаги наугад.
- `--locked` оставляем: он и сейчас там, и он же ловит дрейф `uv.lock`. Если сборка упадёт на `--locked` — это сигнал, что lock разъехался с `pyproject.toml`, а не повод убрать флаг.
- Docker-кэш слоёв не помешает: текст `RUN`-команды меняется, слой пересобирается. Cache-mount `/root/.cache/uv` кэширует только скачанные дистрибутивы и на состав `.venv` не влияет.
- Ручные кейсы приёмки трека живут в `tracks/T2/test-cases.md` (авторит `test-author`), автотестов нет — это зафиксировано партицией брифа.

## Open Questions

Все вопросы закрыты оркестратором до PLAN_REVIEW; резолюции ниже.

1. **Исходники и тесты в прод-образах — расширять ли скоуп трека?** ЗАКРЫТ: реализуем строго бриф — `COPY` не трогаем (правка состава образа сверх брифа = решение, не покрытое дизайном; whitelist эскалации № 1 запрещает брать его автономно). Наблюдение уходит кандидатом в backlog через `## Follow-ups` summary трека → harvester (P3, категория та же, что у dev-deps: тестовый и чужой код в прод-образе).
2. **Формулировка брифа § 4 про «финальный sync их не удаляет».** ЗАКРЫТ: бриф не правится в конвейере (design-brief — артефакт архитектора; вывод «править оба вызова» верен, неточна только механика доказательства). Уточнение формулировки — кандидат для pre-commit gate; верификация плана уже усилена проверкой размера RUN-слоя кэша (`docker history`), которая и отличает правку одного вызова от правки обоих.

## Правки по итогам PLAN_REVIEW

- **[blocker]** Убраны импорты virtual-членов workspace из верификации T2.2: `siem_service` — из позитивного списка (шаг 1), `app` — из must-fail-списка (шаг 2, vacuous). Вместо них — `ls /app/backend` (ожидается только `pyproject.toml`). В Согласованные факты добавлен пункт про `source = { virtual = … }` и явный запрет добавлять `[build-system]` в pyproject'ы вне скоупа.
- **[question]** Критерий шага 3 в обеих фазах сужен: провал — только `Installed N packages` и имена dev-пакетов; `Resolved N packages` под `--network none` — ожидаемая офлайн-валидация lock'а. `UV_FROZEN` не вводится.
- **[nit]** Шаг 4 в обеих фазах переведён с суммарного размера образа на размер RUN-слоя кэша через `docker history --no-trunc` — суммарный размер не различал правку одного вызова и обоих. Согласованные факты и «Артефакт для summary» приведены в соответствие.
- **[nit]** В T2.2 Изменения 4 снято приглашение уточнять комментарий `services/siem-service/Dockerfile:29-31` — он остаётся дословно.
