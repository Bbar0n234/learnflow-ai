# Test Cases: chore-001 — прод-закрытие / трек T2 (прод-образы без dev-зависимостей)

Трек чистит два прод-образа: `backend/Dockerfile` и `services/siem-service/Dockerfile` теперь синкают окружение как `uv sync --locked --no-dev --package <свой пакет>` (в **обоих** вызовах — кэш-слое и финальном), а оба `entrypoint.sh` экспортируют `UV_NO_SYNC=1`, чтобы `uv run` не пересинкал окружение при старте контейнера и не вернул dev-группу обратно. Python-код, compose, env-файлы и CI трек не трогает — меняется только состав собираемых образов.

Кейсы ниже подтверждают четыре вещи и страхуют от четырёх способов сделать правку бесполезной. Подтверждаем: (1) оба образа собираются; (2) рантайм цел — всё, что нужно `alembic` и `uvicorn` для старта, в образе осталось; (3) dev-группа (`pytest`, `mypy`, `ruff`, `pre-commit`, `testcontainers`, `learnflow-testing`) из образов ушла, а из siem-образа ушёл ещё и чужой стек backend'а (`langchain*`, `langgraph*`, `langfuse`, `psycopg`), код которого туда не копируется; (4) контейнер при старте окружение не пересинкивает. Страхуем от: правки только финального `uv sync` при нетронутом кэш-слое (файлы остаются в образе под whiteout — размер и pull-трафик не падают), забытого `UV_NO_SYNC`, поломки рантайма чрезмерным `--no-dev`, выхода за файловый скоуп трека.

**Чего кейсы сознательно не проверяют.** `import app` (backend) и `import siem_service` (siem) через интерпретатор образа не проверяются ни как позитивный, ни как негативный сигнал: оба пакета — virtual-члены workspace (`source = { virtual = … }` в `uv.lock`, нет `[build-system]`), uv их в `.venv` не ставит ни до правки, ни после; код приходит в рантайм прямо с диска через `uv run … --app-dir …`. Импорт `app` в siem-образе дал бы «отсутствует» независимо от результата трека (vacuous), импорт `siem_service` провалил бы корректную реализацию. Дырку закрывает кейс `{T2.9}` (`ls /app/backend`). Если кейс подталкивает добавить `[build-system]` в чей-то `pyproject.toml` — это выход за скоуп трека и повод эскалировать, а не «починить».

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры** (применять, если итерация их касается): `📊` — проверка наблюдаемости (структура БД, метрики, Redis state, Langfuse); `🔴` — проверка реальных инъекций / атак / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `tests/<scope>/`); `*(регресс)*` — кейс страхует «поведение не сломалось» (отделяет регресс от проверки нового поведения).
- **run-log** (только у перепрогнанных кейсов) — строка-история флипов с причиной:
  `runs: r1 ✅ → r2 ❌ (после фикса review #3: регрессия инвалидации) → r3 ✅`.
  Один прогон — run-log не нужен. Перепрогон после правки кода обязателен (см. ре-верификацию).

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`/`make check-fe`/`make test`) — перепрогон всегда; ручные/UI-кейсы — перепрогон только затронутой области. Каждый перепрогон → запись в run-log. Для этого трека «затронутая область» читается пофазно: правка `backend/Dockerfile` или `backend/entrypoint.sh` аннулирует `{T2.1}`–`{T2.5}` (образ надо пересобрать), правка siem-файлов — `{T2.6}`–`{T2.11}`.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики: не сошлось — повтори (мог быть транзиент); не сошлось второй раз — fail + эскалация, без долгой отладки. Инструменты этого трека: stdout контейнера, `docker history --no-trunc`, `docker image ls`, содержимое `/app/.venv/bin` и `/app/backend`. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer** (A6: fixer ≠ автор теста), не сам тестировщик.

**Скоуп по трекам.** Кейсы с префиксом трека (`{T2.1}`) гоняются на своём треке + Layer 0; cross-cutting (Layer 2/3 без префикса) — в INTEGRATION_TEST (`{track_id}=final`). Не пропускать кейсы молча — неприменимый помечать причиной.

### Процесс

Стенд поднимать **не нужно и нельзя**: Layer 1 целиком закрывается `docker build` и разовыми `docker run --rm`. Ограничения, обязательные к соблюдению на Layer 1:

1. **`docker compose up / down / restart / stop` запрещены** на всё время прогона Layer 1: в этом worktree параллельные треки держат testcontainers-БД, остановка стека уронит их прогон. `docker build -f <dockerfile> -t <tag> .` и `docker run --rm …` состояние compose не трогают.
2. **Свои теги.** Все образы собирать с суффиксом `t2-verify` (и `t2-before` для baseline). Compose в этом проекте собирает образы без явного `image:` и именует их сам (`<project>_<service>`), поэтому теги `t2-*` ни с чем не столкнутся — но только пока не используются голые имена вроде `backend:latest`.
3. **Build context — корень репозитория** (`.`), команды запускать из корня worktree. Контекст берётся из рабочего дерева, а в нём живут незакоммиченные правки параллельных треков (T1/T3/T4 трогают `backend/app/**`, `.env*`, `docker-compose.yml`). На состав `.venv` это не влияет, но может менять причину падения контейнера в кейсах `{T2.4}` / `{T2.10}` — критерий там сформулирован так, чтобы от конкретной ошибки не зависеть.
4. **Sandbox и сеть.** `docker build` исполняет демон вне bash-sandbox (CLI ходит к нему через unix-сокет), сетевая изоляция bash-команд этому не мешает. Кейсам `{T2.4}` / `{T2.10}` нужен **выход контейнера в сеть** (uv должен иметь возможность реально доставить пакеты — иначе проверка «не пересинкал» вырождается в «не смог»); там, где ниже встречается `--network none`, это необязательный дополнительный прогон, а не основной шаг. Нет сети — эти два кейса помечаются deferred с причиной, а не «пройдено».
5. Сборка обоих образов — минуты; кэш слоёв и cache-mount `/root/.cache/uv` переиспользуются, повторные прогоны быстрее.

Layer 2/3 гоняются в INTEGRATION_TEST после барьера — там compose уже разрешён и запрет п. 1 снят.

**Часть кейсов уже фактически исполнена implementer'ом** при реализации трека — цифры и результаты лежат в [summary.md](summary.md) § Verification. Такие кейсы помечены `*(исполнен при IMPLEMENT: summary § …)*`. Решение, перепрогонять их или засчитать со ссылкой, — за тестировщиком; основание для «засчитать» есть только у кейсов, чей артефакт с тех пор не пересобирался и чьи входные файлы не правились. Три исключения, где засчитывать по summary **нельзя**: `{T2.4}` и `{T2.10}` — implementer гонял их без обязательного теперь негативного контроля (шаг B), поэтому кейсы перепрогоняются целиком и с сетью; `{T2.12}` — границы там подтверждал автор правок, что снимает с проверки её смысл (A6). Кейсы `{T2.5}` / `{T2.11}` (размеры слоёв) при перепрогоне дадут другие абсолютные цифры на другой машине — значим не абсолют, а критерий.

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Состав окружения образа | `docker run --rm --entrypoint /app/.venv/bin/python <tag> -c "import …"` |
| Консольные скрипты образа | `docker run --rm --entrypoint ls <tag> /app/.venv/bin` |
| Слои и их размеры | `docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' <tag>` |
| Суммарный размер образа | `docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.Size}}'` |
| Поведение старта | stdout `docker run --rm -e <минимум настроек> <tag>` (с сетью — см. `{T2.4}` шаг C) |
| Реальность пересинка (контроль) | `docker run --rm --entrypoint uv <tag> run python -c "import pytest"` |
| Цифры implementer'а | [summary.md](summary.md) § Verification, § Размеры |

---

## Дизайн автотестов

**Автотестов у трека нет — ни одного, и это решение, а не пропуск.** Оно зафиксировано партицией брифа (строка T2: «автотест-скоупа нет») и следует из `testing.md` § Граница авто / ручное, где ручные кейсы оставлены под длинный хвост тяжело автоматизируемого.

Причина в том, где живёт объект проверки. Трек не меняет ни строчки Python — он меняет **состав собранного docker-образа**. Утверждение, которое надо проверить («в `/app/.venv` нет `pytest`, есть `uvicorn`, а слой кэша похудел»), нельзя высказать изнутри pytest-процесса: чтобы получить объект, тесту пришлось бы вызвать `docker build` (минуты, сеть за дистрибутивами, cache-mount'ы) и затем `docker run`. Такой тест проверял бы не наш код, а артефакт сборки, и по стилю из `testing.md` был бы прямым антипаттерном — медленный, зависящий от внешнего демона и от того, что лежит в кэше слоёв. Отдельная ирония: штатный шов к докер-демону у нас — `testcontainers`, а он сам член dev-группы, то есть ровно того, что трек из образов и выносит.

Вторая причина — характер изменения. Это разовая правка конфигурации сборки, а не поведение, которое может отрефакториться и незаметно уехать. Регрессию здесь ловит не тест, а сама сборка (упадёт, если флаги несовместимы) плюс ревью диффа четырёх файлов.

**Осознанно не покрываем автотестом** — триадами *(что — почему — куда уехало)*:

- Состав `.venv` в прод-образах (рантайм цел / dev-группы и чужого стека нет) — объект существует только после `docker build`, у pytest-набора нет к нему шва, а прогон занимает минуты — → ручные `{T2.2}`, `{T2.3}`, `{T2.7}`, `{T2.8}`, `{T2.9}`.
- Отсутствие пересинка окружения при старте контейнера — наблюдаемо только на реальном старте контейнера, причём с доступным индексом пакетов: без сети установка невозможна физически, и «не пересинкал» становится неотличимо от «не смог», внутри процесса теста воспроизводится лишь имитация — → ручные `{T2.4}`, `{T2.10}` (там это оформлено парой шагов: негативный контроль доказывает, что пересинк возможен, и только после него целевой прогон что-то значит).
- Размер RUN-слоя кэша (дискриминатор «поправлены оба `uv sync`, а не только финальный») — абсолютные байты зависят от машины, версии базового образа и содержимого кэша дистрибутивов; порог в гейте дал бы флак, а не сигнал — → ручные `{T2.5}`, `{T2.11}` со сверкой критерия (а не абсолюта) и цифрами в summary.
- Страж «никто не вернул `--all-packages` в Dockerfile» (grep по тексту сборочных файлов в CI) — → ручные `{T2.5}`, `{T2.11}` плюс ревью диффа. Оба кейса проверяют слой двумя разными критериями, и смешивать их не надо: критерий **(а)** — тоже текстовая сверка, только не по исходному Dockerfile, а по `CreatedBy` слоёв собранного образа, и сверяет она **контрактные флаги из брифа § 4** (`--no-dev` + `--package` в обоих `uv sync`); критерий **(б)** — уже эффект, размер RUN-слоя. Держать (а) стоит, потому что форму предписывает бриф, а не наша реализация. Следствие, важное для тестировщика: эквивалентная по смыслу запись (`ENV UV_NO_DEV=1` вместо флага) критерий (а) провалит при выполненном (б) — это повод эскалировать расхождение с брифом, а не «чинить» кейс.
- Работоспособность полного стека, собранного из прод-образов — нужен `docker compose` и живая инфра (Postgres, Redis), на Layer 1 compose запрещён параллельным треком — → cross-cutting кейс Layer 2 в INTEGRATION_TEST.

Автоматизировать это в принципе возможно — отдельной CI-джобой, которая собирает оба образа и прогоняет по ним ту же инспекцию, что кейсы ниже. Это самостоятельный контур со своей стоимостью прогона и своим решением о том, на каких событиях он запускается; в рамках трека он не заводится, и перечисленное выше остаётся непокрытым автоматикой по названным причинам.

**Замеченные прод-баги (для fixer'а, сам не чиню):** нет — файлы трека прочитаны, правки соответствуют плану и брифу.

### Layer 0: Automated gate

- [ ] `make check` / `make test` — **неприменимо к треку T2**: файловый скоуп трека — два `Dockerfile` и два `entrypoint.sh`, Python-кода трек не касается, транзитивных эффектов на статанализ и тесты нет (проверено ревьюером партиции). Гейт гоняют треки, меняющие код (T1/T3/T4); дублировать его здесь — прогонять чужой незакоммиченный код под своим статусом.
- [ ] `make check-fe` — неприменимо: фронтенд трек не трогает (стадия `frontend-build` в `backend/Dockerfile` не меняется).

---

## Ручные кейсы + статусы

### Layer 1A: Трек T2, фаза T2.1 — backend-образ

- [x] `{T2.1}` **Backend-образ собирается.** Перепрогнан тестировщиком (образов implementer'а в демоне не осталось, а `{T2.2}`–`{T2.5}` без образа неисполнимы). `docker build -f backend/Dockerfile -t learnflow-backend:t2-verify .` — exit 0, падений на `--locked` нет; `docker image ls` → `learnflow-backend:t2-verify 719MB`, ровно цифра из summary.
  **Предусловие**: рабочая директория — корень worktree; правки трека на месте; демон docker доступен.
  **Команды**:
  ```bash
  docker build -f backend/Dockerfile -t learnflow-backend:t2-verify .
  docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep learnflow-backend
  ```
  **Ожидание**: сборка завершается с кодом 0; в выводе `docker image ls` есть `learnflow-backend:t2-verify`; размер — порядка цифры из summary (719MB), заметное расхождение фиксируется в результате.
  **Провал**: ненулевой код сборки. Отдельно фиксировать падение на `--locked` — это сигнал дрейфа `uv.lock` относительно `pyproject.toml`, а **не** повод убрать флаг; такой отказ эскалируется, флаги наугад не подбираются.
  *(исполнен при IMPLEMENT: summary § Verification T2.1, § Размеры)*

- [x] `{T2.2}` **Рантайм backend-образа цел** *(регресс)*. Перепрогнан на пересобранном образе. `import uvicorn, alembic, fastapi, langgraph, langfuse, psycopg, redis, siem_contracts` через `/app/.venv/bin/python` → `runtime ok`, exit 0; `alembic --version` → `alembic 1.18.4`, exit 0; `uvicorn --version` → `Running uvicorn 0.41.0 with CPython 3.12.13 on Linux`, exit 0. `ModuleNotFoundError` нет ни на одном имени — `--no-dev` рантайм не срезал.
  **Предусловие**: `{T2.1}` пройден.
  **Команды** (абсолютный путь к интерпретатору обязателен: в backend-образе `PATH` на `/app/.venv/bin` **не** настроен, `--entrypoint python` возьмёт системный интерпретатор без site-packages и «провалит» вообще всё — ложноположительный результат):
  ```bash
  docker run --rm --entrypoint /app/.venv/bin/python learnflow-backend:t2-verify \
    -c "import uvicorn, alembic, fastapi, langgraph, langfuse, psycopg, redis, siem_contracts; print('runtime ok')"
  docker run --rm --entrypoint /app/.venv/bin/alembic learnflow-backend:t2-verify --version
  docker run --rm --entrypoint /app/.venv/bin/uvicorn learnflow-backend:t2-verify --version
  ```
  **Ожидание**: все три команды — код 0, первая печатает `runtime ok`.
  **Провал**: любой `ModuleNotFoundError` или ненулевой код — `--no-dev` срезал то, что нужно рантайму (`alembic` и `uvicorn[standard]` объявлены в `[project.dependencies]`, поэтому срезаться не должны).
  *(исполнен при IMPLEMENT: summary § Verification T2.1, шаг 1)*

- [x] `{T2.3}` **Dev-группы в backend-образе нет.** Контрольная строка — `control ok: шов живой (uvicorn найден)`, то есть цикл достоверен. Все семь модулей `ok: … absent`: `pytest`, `_pytest`, `testcontainers`, `learnflow_testing`, `factory`, `mypy`, `asyncpg` — последний подтверждает, что сработал именно `--package` (чужая зависимость siem-service в образ не заехала), а не один `--no-dev`. В `/app/.venv/bin` — 30 записей, ни `pytest`, ни `ruff`, ни `mypy`, ни `pre-commit`, ни `lint-imports` (только рантайм: `alembic`, `dotenv`, `fastapi`, `httpx`, `mcp`, `openai`, `uvicorn`, `watchfiles`, `websockets`, `python*`, `activate*` и утилиты транзитивных зависимостей).
  **Предусловие**: пройдены `{T2.1}` (образ собран) **и** `{T2.2}` — последний и есть позитивный контроль шва: он доказывает, что `/app/.venv/bin/python` в этом образе существует и импортирует установленное. Без него цикл ниже даёт false-green: `>/dev/null 2>&1` глотает любую причину ненулевого кода, и опечатка в теге, кривой путь интерпретатора или несобравшийся образ выдадут `ok: … absent` разом по всем строкам.
  **Команды** — контрольная строка первой, цикл только после неё:
  ```bash
  docker run --rm --entrypoint /app/.venv/bin/python learnflow-backend:t2-verify -c "import uvicorn" \
    >/dev/null 2>&1 && echo "control ok: шов живой (uvicorn найден)" \
                    || echo "CONTROL FAILED: цикл ниже недостоверен, кейс не засчитывать"
  for m in pytest _pytest testcontainers learnflow_testing factory mypy asyncpg; do
    docker run --rm --entrypoint /app/.venv/bin/python learnflow-backend:t2-verify -c "import $m" \
      >/dev/null 2>&1 && echo "FAIL: $m present" || echo "ok: $m absent"
  done
  docker run --rm --entrypoint ls learnflow-backend:t2-verify /app/.venv/bin
  ```
  **Ожидание**: контрольная строка — `control ok`; все семь строк цикла — `ok: … absent`; в листинге `/app/.venv/bin` нет `pytest`, `ruff`, `mypy`, `pre-commit`, `lint-imports`. `asyncpg` в списке не случайно: это зависимость только siem-service, её отсутствие — сигнал, что сработал именно `--package`, а не один `--no-dev`.
  **Провал**: `CONTROL FAILED` (кейс недостоверен — сначала чинить шов/тег/образ, потом перепрогонять), любая строка `FAIL: … present` либо dev-скрипт в листинге.
  *(исполнен при IMPLEMENT: summary § Verification T2.1, шаг 2)*

- [x] `{T2.4}` **Backend-entrypoint не пересинкивает окружение при старте.** Перепрогнан целиком и **с сетью** (все три шага, как предписано). Шаг A: `grep -n UV_NO_SYNC /app/entrypoint.sh` → `6:export UV_NO_SYNC=1`. Шаг B (негативный контроль): `--entrypoint uv … run python -c "import pytest"` → exit **0**, напечатано `resync happened`, и в выводе реальная установка — `Installed 35 packages in 404ms` с загрузкой `mypy`, `ruff`, `virtualenv`, `faker` и сборкой `learnflow-testing`. Все три признака на месте: индекс достижим, пересинк в этом образе физически возможен, значит шаг C дискриминирует. Шаг C (те же условия, работает `entrypoint.sh`): вывод начинается с `Running database migrations...`, контейнер падает с exit 1 на `ValidationError: 1 validation error for Settings / jwt_secret Field required`. В полном логе прогона нет ни одной строки `Installed N packages` / `Resolved N packages` и ни одного имени dev-пакета (`pytest`, `mypy`, `ruff`, `pre-commit`, `testcontainers`) — при доступном индексе окружение не пересинкалось.
  Кейс состоит из трёх обязательных шагов, и порядок важен: шаг A закрывает требование брифа, шаг B доказывает, что пересинк вообще возможен в этом образе, и только после него шаг C становится дискриминатором. Без шага B шаг C вакуозен: cache-mount `/root/.cache/uv` в слои образа не попадает, поэтому в изолированном от сети контейнере колёс dev-группы взять неоткуда — `uv run` упал бы на сетевой ошибке и без `UV_NO_SYNC`, а кейс засчитал бы это как успех.
  **Предусловие**: пройдены `{T2.1}` и `{T2.3}` (последний — чтобы шаг B не прошёл вакуозно: если `pytest` уже лежит в образе, импорт удастся и без синка); для шагов B и C нужен **выход в сеть** (uv ходит на индекс за дистрибутивами). Сети нет — кейс не «пройден», а **deferred** с этой причиной: `grep` в одиночку доказывает наличие строки в файле, но не её эффект.
  **Шаг A — требование брифа (`UV_NO_SYNC=1` есть в entrypoint'е образа)**:
  ```bash
  docker run --rm --entrypoint grep learnflow-backend:t2-verify -n UV_NO_SYNC /app/entrypoint.sh
  ```
  Ожидание: найден `export UV_NO_SYNC=1`. Провал: строки нет.
  **Шаг B — негативный контроль (обязателен): без экспорта пересинк реален**:
  ```bash
  docker run --rm --entrypoint uv learnflow-backend:t2-verify run python -c "import pytest; print('resync happened')" ; echo "exit=$?"
  ```
  `--entrypoint uv` минует `entrypoint.sh`, поэтому `UV_NO_SYNC` не экспортирован. Форма без `--package` выбрана намеренно: она зеркалит первый `uv run` реального backend-entrypoint'а (`uv run alembic -c backend/alembic.ini upgrade head` — тоже без `--package`). WORKDIR образа — `/app`, корневой `pyproject.toml` держит `pytest` в dev-группе, значит uv доставит её и импорт пройдёт.
  Ожидание: код **0**, напечатано `resync happened`, **и** в выводе видна установка (`Installed N packages`) — все три признака обязательны; успешный импорт без строки установки означает, что `pytest` уже был в образе (провал `{T2.3}`), а не что контроль сработал. Провал: команда упала — тогда шов не работает по причине, не связанной с треком (нет сети, недоступен индекс, сломан образ), и шаг C ничего не докажет; кейс переводится в deferred с зафиксированной причиной, а не засчитывается.
  **Шаг C — целевая проверка: entrypoint при тех же условиях пересинка не делает**:
  ```bash
  docker run --rm \
    -e DATABASE_URL=postgresql+psycopg://x:x@127.0.0.1:5432/x \
    learnflow-backend:t2-verify
  ```
  Условия те же, что в шаге B (сеть есть, индекс достижим) — разница ровно одна: работает `entrypoint.sh` со своим `export UV_NO_SYNC=1`.
  Ожидание: печатается `Running database migrations...`, затем контейнер падает — на недоступной БД либо на валидации обязательных настроек (`ValidationError`). **Конкретная ошибка неважна**: конфигурация намеренно неполная, а в контексте сборки живут незакоммиченные правки параллельных треков, которые могут менять состав обязательных настроек.
  **Провал шага C** (точная формулировка — чтобы не завалить корректную реализацию): в выводе есть строка `Installed N packages` **или** имена dev-пакетов (`pytest`, `mypy`, `ruff`, `pre-commit`, `testcontainers`) — то есть при доступном индексе окружение всё-таки пересинкалось. Строка `Resolved N packages` провалом **не считается**: `UV_NO_SYNC` гасит синк окружения, а не сверку `uv.lock`; её отсутствие — тоже норма. Требовать `UV_FROZEN` для подавления `Resolved` не нужно — это сверх брифа.
  **Дополнительно (необязательно)**: тот же прогон под `--network none` — контейнер обязан дойти до `Running database migrations...` не пытаясь ничего ставить; шаг подтверждает, что офлайн-старт не зависит от индекса, но дискриминатором `UV_NO_SYNC` **не является**.
  *(шаги A и C исполнены при IMPLEMENT под `--network none`: summary § Verification T2.1, шаг 3 — падение на валидации `jwt_secret`. Шаг B implementer'ом не выполнялся, поэтому засчитать кейс по summary нельзя: перепрогон обязателен, целиком, с сетью)*

- [x] `{T2.5}` **Кэш-слой backend-образа похудел — оба `uv sync` поправлены, а не только финальный.** Baseline построен по рецепту: `git log -1 -- backend/Dockerfile` → `113649e`, `grep -c -- '--all-packages'` = **2** (взят до-трековый вариант), собран как `learnflow-backend:t2-before`. Критерий (а) — оба RUN-слоя с `uv sync` в `t2-verify` несут контрактную пару флагов: кэш-слой `uv sync --locked --no-dev --no-install-workspace --package learnflow-backend` (145MB) и финальный `uv sync --locked --no-dev --package learnflow-backend` (2.47MB); эквивалентных записей вроде `ENV UV_NO_DEV=1` нет, эскалация не требуется. Критерий (б) — кэш-слой 268MB (`t2-before`, `--all-packages`) → **145MB** (`t2-verify`), дельта −123MB, строго меньше. Суммарный размер (критерием не является, для протокола): 842MB → 719MB. Цифры совпали с summary до последнего знака.
  Это единственный кейс, различающий правку обоих вызовов и правку одного: docker-слои кумулятивны, поэтому финальный `uv sync` (он exact и лишнее из venv убирает) кладёт поверх файлов кэш-слоя лишь whiteout — файлы остаются в образе, а суммарный размер почти не меняется. Смотреть надо на конкретный RUN-слой.
  **Предусловие**: `{T2.1}` пройден; доступен git-baseline файла до правок трека.
  **Команды** — сначала baseline (правки трека на момент написания кейсов не закоммичены, поэтому baseline берётся из последнего коммита, тронувшего файл; проверка `grep` подтверждает, что взят именно до-трековый вариант):
  ```bash
  TMP=$(mktemp -d)
  BASE=$(git log -1 --format=%H -- backend/Dockerfile)
  git show "$BASE:backend/Dockerfile" > "$TMP/Dockerfile.backend.before"
  grep -c -- '--all-packages' "$TMP/Dockerfile.backend.before"   # ожидание: 2
  # если 0 — правки трека уже закоммичены; взять предыдущий коммит:
  #   BASE=$(git log --format=%H -- backend/Dockerfile | sed -n 2p)
  docker build -f "$TMP/Dockerfile.backend.before" -t learnflow-backend:t2-before .
  docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' learnflow-backend:t2-before
  docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' learnflow-backend:t2-verify
  ```
  **Ожидание**: (а) **текстовая сверка контрактных флагов** — в истории `t2-verify` **оба** RUN-слоя с `uv sync` несут `--no-dev --package learnflow-backend`: кэш-слой (тот, чей `CreatedBy` содержит `--no-install-workspace`) и финальный. Именно эту пару флагов предписывает бриф § 4, поэтому сверка текста здесь — проверка контракта, а не реализации; (б) **эффект** — размер кэш-слоя в `t2-verify` **строго меньше**, чем размер соответствующего `--all-packages`-слоя в `t2-before` (у implementer'а — 268MB → 145MB). Обе цифры и дельта идут в результат кейса.
  **Провал**: размеры кэш-слоя совпали (кэш-слой не поправлен) либо хотя бы один из двух `uv sync` в истории образа идёт без `--no-dev --package`. Суммарный размер образа критерием **не является** — он «пройдёт» и при непоправленном кэш-слое. Отдельный случай: если критерий (б) выполнен, а (а) провален из-за **эквивалентной** записи (например `ENV UV_NO_DEV=1` вместо флага) — это не «починить кейс», а эскалация архитектору: бриф предписывает конкретную форму, и расхождение решается им, а не тестировщиком.
  *(исполнен при IMPLEMENT: summary § Verification T2.1 шаг 4 и § Размеры — 268MB → 145MB; при перепрогоне на другой машине абсолютные цифры могут отличаться, значим критерий «строго меньше» и наличие флагов в обоих слоях)*

### Layer 1B: Трек T2, фаза T2.2 — siem-образ

- [x] `{T2.6}` **Siem-образ собирается.** Перепрогнан тестировщиком. `docker build -f services/siem-service/Dockerfile -t siem-service:t2-verify .` — exit 0, резолвер на членах workspace не падал; `docker image ls` → `siem-service:t2-verify 256MB`, ровно цифра из summary.
  **Предусловие**: то же, что в `{T2.1}`.
  **Команды**:
  ```bash
  docker build -f services/siem-service/Dockerfile -t siem-service:t2-verify .
  docker image ls --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep siem-service
  ```
  **Ожидание**: код 0; образ `siem-service:t2-verify` есть, размер порядка цифры из summary (256MB).
  **Провал**: ненулевой код. Отдельно фиксировать падение резолвера на отсутствующем члене workspace — это значит, что из Dockerfile убрали bind-mount или `COPY backend/pyproject.toml`; uv требует существования на диске каждого члена из `[tool.uv.workspace] members` независимо от `--package`.
  *(исполнен при IMPLEMENT: summary § Verification T2.2, § Размеры)*

- [x] `{T2.7}` **Рантайм siem-образа цел** *(регресс)*. `import uvicorn, alembic, fastapi, pydantic_settings, asyncpg, sqlalchemy, redis, structlog, jwt, siem_contracts` через `/app/.venv/bin/python` → `runtime ok`, exit 0; `alembic --version` → `alembic 1.18.4`, exit 0. `ModuleNotFoundError` нет.
  **Предусловие**: `{T2.6}` пройден.
  **Команды** (абсолютный путь — для единообразия с backend-кейсами; в siem-образе `PATH` настроен, но полагаться на это не нужно):
  ```bash
  docker run --rm --entrypoint /app/.venv/bin/python siem-service:t2-verify \
    -c "import uvicorn, alembic, fastapi, pydantic_settings, asyncpg, sqlalchemy, redis, structlog, jwt, siem_contracts; print('runtime ok')"
  docker run --rm --entrypoint /app/.venv/bin/alembic siem-service:t2-verify --version
  ```
  **Ожидание**: обе команды — код 0, первая печатает `runtime ok`.
  **Провал**: любой `ModuleNotFoundError`. `siem_service` в списке импортов отсутствует намеренно — см. преамбулу: это virtual-член workspace, в `.venv` его нет и с корректной правкой не будет.
  *(исполнен при IMPLEMENT: summary § Verification T2.2, шаг 1)*

- [x] `{T2.8}` **В siem-образе нет ни dev-группы, ни чужого стека backend'а.** Контрольная строка — `control ok: шов живой (uvicorn найден)`. Все восемь модулей `ok: … absent`: `langgraph`, `langchain`, `langchain_core`, `langfuse`, `psycopg`, `pytest`, `testcontainers`, `learnflow_testing` — весь LangChain/LangGraph/Langfuse/psycopg-стек, заезжавший через `--all-packages`, отсечён. В `/app/.venv/bin` ровно 20 записей и только рантайм своего пакета: `alembic`, `dotenv`, `fastapi`, `mako-render`, `python*`, `uvicorn`, `watchfiles`, `websockets`, `activate*`, `pydoc.bat` — совпадает с листингом из summary, ничего постороннего.
  **Предусловие**: пройдены `{T2.6}` **и** `{T2.7}` — позитивный контроль шва (см. `{T2.3}`: без него ненулевой код по любой посторонней причине читается как «пакета нет» и красит весь кейс в false-green).
  **Команды** — контрольная строка первой, цикл только после неё:
  ```bash
  docker run --rm --entrypoint /app/.venv/bin/python siem-service:t2-verify -c "import uvicorn" \
    >/dev/null 2>&1 && echo "control ok: шов живой (uvicorn найден)" \
                    || echo "CONTROL FAILED: цикл ниже недостоверен, кейс не засчитывать"
  for m in langgraph langchain langchain_core langfuse psycopg pytest testcontainers learnflow_testing; do
    docker run --rm --entrypoint /app/.venv/bin/python siem-service:t2-verify -c "import $m" \
      >/dev/null 2>&1 && echo "FAIL: $m present" || echo "ok: $m absent"
  done
  docker run --rm --entrypoint ls siem-service:t2-verify /app/.venv/bin
  ```
  **Ожидание**: контрольная строка — `control ok`; все восемь строк цикла — `ok: … absent`; в `/app/.venv/bin` только рантайм-скрипты своего пакета (у implementer'а — `alembic`, `dotenv`, `fastapi`, `mako-render`, `python*`, `uvicorn`, `watchfiles`, `websockets`, `activate*`), ничего из dev- и backend-инструментария.
  **Провал**: `CONTROL FAILED`, любая строка `FAIL: … present` либо посторонний скрипт в листинге. Это основной кейс трека по эффекту: именно здесь видно, что `--package siem-service` отсёк весь LangChain/LangGraph/Langfuse/psycopg-стек, который раньше заезжал через `--all-packages`.
  *(исполнен при IMPLEMENT: summary § Verification T2.2, шаг 2)*

- [x] `{T2.9}` **Код backend'а в siem-образ не заехал.** `ls /app/backend` → ровно одна строка `pyproject.toml`, exit 0. Ни `app/`, ни `tests/`, ни `alembic/`; каталог на месте, значит `COPY backend/pyproject.toml` цел и workspace-резолвер удовлетворён.
  **Предусловие**: `{T2.6}` пройден.
  **Команды**:
  ```bash
  docker run --rm --entrypoint ls siem-service:t2-verify /app/backend
  ```
  **Ожидание**: ровно одна строка — `pyproject.toml`. Он там обязан быть: `COPY backend/pyproject.toml /app/backend/pyproject.toml` удовлетворяет workspace-резолвер uv, не таща исходники.
  **Провал**: в листинге есть что-либо кроме `pyproject.toml` (например `app/`, `tests/`, `alembic/`) либо каталог отсутствует целиком (`ls` падает — сломан `COPY`, резолвер останется без члена workspace).
  *(исполнен при IMPLEMENT: summary § Verification T2.2, шаг 2 — `/app/backend` содержит ровно одну запись)*

- [x] `{T2.10}` **Siem-entrypoint не пересинкивает окружение при старте.** Перепрогнан целиком и **с сетью**. Шаг A: `grep -n UV_NO_SYNC /app/entrypoint.sh` → `6:export UV_NO_SYNC=1`. Шаг B (негативный контроль, зеркало шага C — `uv run --package siem-service`): exit **0**, `resync happened`, и реальная установка — `Installed 31 packages in 425ms` со сборкой `learnflow-testing` и загрузкой `zstandard`, `pygments`, `faker`. Все три признака на месте. Шаг C: вывод начинается с `Running siem-service database migrations...`, контейнер падает с exit 1 на `ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)`. В полном логе нет ни `Installed N packages`, ни `Resolved N packages`, ни имён dev-пакетов — при доступном индексе пересинка не было.
  Структура и логика — как в `{T2.4}` (три обязательных шага; шаг B делает шаг C дискриминирующим), отличаются только образ и переменные окружения.
  **Предусловие**: пройдены `{T2.6}` и `{T2.8}` (последний — чтобы шаг B не прошёл вакуозно: если `pytest` уже лежит в образе, импорт удастся без всякого синка); для шагов B и C нужен выход в сеть. Сети нет — кейс deferred с этой причиной, не «пройден».
  **Шаг A — требование брифа**:
  ```bash
  docker run --rm --entrypoint grep siem-service:t2-verify -n UV_NO_SYNC /app/entrypoint.sh
  ```
  Ожидание: найден `export UV_NO_SYNC=1`.
  **Шаг B — негативный контроль (обязателен)**. Форма вызова зеркалит шаг C: `--package siem-service` — ровно то, с чем ходит настоящий entrypoint, так что контроль проверяет тот же путь резолвинга, а не соседний:
  ```bash
  docker run --rm --entrypoint uv siem-service:t2-verify \
    run --package siem-service python -c "import pytest; print('resync happened')" ; echo "exit=$?"
  ```
  Ожидание: код **0**, напечатано `resync happened`, **и в выводе видна установка** (`Installed N packages`) — все три признака обязательны. `--entrypoint uv` минует `entrypoint.sh`, поэтому `UV_NO_SYNC` не экспортирован, и uv доставляет dev-группу пакета `siem-service` (`learnflow-testing` → `pytest`). Отсутствие `Installed N packages` при успешном импорте означает, что `pytest` уже лежал в образе, — это провал `{T2.8}`, а не успех контроля. Падение команды — кейс deferred с зафиксированной причиной.
  **Шаг C — целевая проверка**:
  ```bash
  docker run --rm \
    -e SIEM_DATABASE_URL=postgresql+asyncpg://x:x@127.0.0.1:5432/x \
    -e SIEM_JWT_SECRET=dummy \
    siem-service:t2-verify
  ```
  Ожидание: печатается `Running siem-service database migrations...`, затем падение на недоступной БД (`ConnectionRefusedError`) или на валидации настроек — конкретная ошибка неважна.
  **Провал шага C**: тот же критерий, что в `{T2.4}` — при доступном индексе в выводе появились `Installed N packages` или имена dev-пакетов. `Resolved N packages` (как и её отсутствие) провалом не считается.
  **Дополнительно (необязательно)**: тот же прогон под `--network none` — подтверждает независимость офлайн-старта от индекса, дискриминатором не является.
  *(шаги A и C исполнены при IMPLEMENT под `--network none`: summary § Verification T2.2, шаг 3 — падение на `ConnectionRefusedError`. Шаг B не выполнялся — перепрогон кейса обязателен, целиком, с сетью)*

- [x] `{T2.11}` **Кэш-слой siem-образа похудел — оба `uv sync` поправлены.** Baseline: `git log -1 -- services/siem-service/Dockerfile` → `113649e`, `grep -c -- '--all-packages'` = **2**, собран как `siem-service:t2-before`. Критерий (а) — оба RUN-слоя `t2-verify` несут контрактные флаги: кэш-слой `uv sync --locked --no-dev --no-install-workspace --package siem-service` (65.3MB) и финальный `uv sync --locked --no-dev --package siem-service` (2.47MB). Критерий (б) — кэш-слой 268MB → **65.3MB**, дельта −202.7MB, сокращение **×4,10** при пороге ×3. Суммарный размер (не критерий): 459MB → 256MB. Цифры совпали с summary.
  Здесь ожидается основная экономия трека: из образа уходит ~108 пакетов чужого стека (цифра из dry-run в плане).
  **Предусловие**: `{T2.6}` пройден.
  **Команды**:
  ```bash
  TMP=$(mktemp -d)
  BASE=$(git log -1 --format=%H -- services/siem-service/Dockerfile)
  git show "$BASE:services/siem-service/Dockerfile" > "$TMP/Dockerfile.siem.before"
  grep -c -- '--all-packages' "$TMP/Dockerfile.siem.before"   # ожидание: 2
  # если 0 — правки трека уже закоммичены; взять предыдущий коммит:
  #   BASE=$(git log --format=%H -- services/siem-service/Dockerfile | sed -n 2p)
  docker build -f "$TMP/Dockerfile.siem.before" -t siem-service:t2-before .
  docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' siem-service:t2-before
  docker history --no-trunc --format '{{.Size}}\t{{.CreatedBy}}' siem-service:t2-verify
  ```
  **Ожидание**: (а) **текстовая сверка контрактных флагов** — оба RUN-слоя с `uv sync` в `t2-verify` несут `--no-dev --package siem-service` (форма предписана брифом § 4); (б) **эффект** — кэш-слой (`--no-install-workspace`) в `t2-verify` меньше своего `--all-packages`-предшественника в `t2-before` **кратно: не менее чем в 3 раза**. Порог не произволен: уходят ~108 пакетов чужого стека, у implementer'а получилось 268MB → 65.3MB (≈ ×4,1). Цифры и дельта — в результат кейса.
  **Провал**: размеры совпали; сокращение есть, но меньше трёхкратного (типичная причина — применён только `--no-dev`, без `--package`: dev-группа ушла, чужой LangChain-стек остался); либо хотя бы один `uv sync` в истории идёт без `--no-dev --package`. Обратите внимание: «`--no-dev` в одиночку» ловится в первую очередь критерием (а) — по отсутствию `--package` в тексте слоя; кратный порог в (б) — вторая линия на случай, если флаги записаны иначе. Как и в `{T2.5}`, расхождение (а) при выполненном (б) из-за эквивалентной записи — эскалация, а не правка кейса.
  *(исполнен при IMPLEMENT: summary § Verification T2.2 шаг 4 и § Размеры — 268MB → 65.3MB; абсолютные цифры машинозависимы, значим критерий)*

### Layer 1C: Границы трека

- [x] `{T2.12}` **Файловый скоуп трека не превышен.** Исполнен тестировщиком (не по summary). Шаг 1: `comm -12` дал ровно четыре файла скоупа — `backend/Dockerfile`, `backend/entrypoint.sh`, `services/siem-service/Dockerfile`, `services/siem-service/entrypoint.sh`; `comm -13` пуст. Шаг 2: цикл по остальным изменённым файлам не выдал ни одной строки `СОВПАДЕНИЕ:` — правок T2-природы вне скоупа нет (в частности чисто в `docker-compose.yml`, `.env*`, `backend/app/**`, которые правят параллельные треки); среди untracked (`--untracked-files=all`, каталоги раскрыты) нет ни Dockerfile'ов, ни entrypoint'ов, ни workflow'ов, ни compose/Makefile. Шаг 3: дифф четвёрки ровно по плану — в каждом Dockerfile `--all-packages` → `--no-dev --package <пакет>` в **обоих** `uv sync`, добавлен комментарий над кэш-слоем (у siem — с дополнением про LangChain-стек), в обоих entrypoint'ах `export UV_NO_SYNC=1` сразу после `set -e` с комментарием. Bind-mount'ы, cache-mount `/root/.cache/uv`, `COPY backend/pyproject.toml` с комментарием, `ENV PATH="/app/.venv/bin:$PATH"` и команды `uv run` не тронуты. `grep 'build-system'` по обоим `pyproject.toml` → `build-system отсутствует — ok`, virtual-члены в packaged не переведены.
  **Кейс исполняет тестировщик — засчитывать по summary нельзя.** В обеих фазах границы подтверждал `git status` самого автора правок; проверка собственных границ автором изменения — ровно та тавтология, против которой стоит A6 (`testing.md` § Целостность тестов). Стоимость перепрогона нулевая: три read-only git-команды, ничего не собирается.
  **Предусловие**: worktree содержит незакоммиченные правки параллельных треков (T1/T3/T4) — их наличие нормально и провалом не является. Проверяется не «сколько файлов изменено», а **принадлежность** правок: все четыре файла скоупа тронуты, и ни один файл вне скоупа не несёт правок T2-природы.
  **Шаг 1 — скоуп трека против фактического диффа** (сверка со списком из брифа, а не с чьим-то отчётом):
  ```bash
  TMP=$(mktemp -d)
  printf '%s\n' backend/Dockerfile backend/entrypoint.sh \
    services/siem-service/Dockerfile services/siem-service/entrypoint.sh | sort > "$TMP/t2-scope.txt"
  git diff --name-only HEAD | sort > "$TMP/changed.txt"
  echo "--- файлы скоупа T2, реально изменённые:"; comm -12 "$TMP/changed.txt" "$TMP/t2-scope.txt"
  echo "--- файлы скоупа T2, НЕ изменённые (ожидание: пусто):"; comm -13 "$TMP/changed.txt" "$TMP/t2-scope.txt"
  ```
  Ожидание: первый список — все четыре файла; второй пуст.
  **Шаг 2 — в сборочных файлах за пределами скоупа нет правок T2-природы.** Проверяется не «упоминание флагов где угодно», а изменение **сборочного** файла (Dockerfile, entrypoint, compose, CI-workflow, Makefile) в духе трека. Документы итерации и конвенции цитируют те же флаги совершенно легитимно: бриф § 4 и партиция приводят `uv sync --locked --all-packages` как исходное состояние, `doc/tech/conventions.md` § Dockerfile правит T1 по партиции. Блок самодостаточен — `$TMP` из шага 1 не наследуется, список скоупа собирается заново:
  ```bash
  TMP=$(mktemp -d)
  printf '%s\n' backend/Dockerfile backend/entrypoint.sh \
    services/siem-service/Dockerfile services/siem-service/entrypoint.sh | sort > "$TMP/t2-scope.txt"
  for f in $(git diff --name-only HEAD | grep -vxFf "$TMP/t2-scope.txt"); do
    case "$f" in
      doc/tasks/iterations/*|doc/tech/conventions.md) continue ;;   # allow-list: артефакты итерации и зона T1
    esac
    git diff -- "$f" | grep -qE 'uv sync|UV_NO_SYNC|--all-packages|--no-dev|--no-install-workspace' \
      && echo "СОВПАДЕНИЕ: $f"
  done
  echo "--- конец шага 2 (ничего выше = чисто)"
  git status --porcelain | grep '^??'   # новые файлы: сборочных среди них быть не должно
  ```
  `-vxFf` (а не `-vFf`) обязателен: без `-x` фильтр отсекает и пути, в которые строка скоупа входит подстрокой.
  **Ожидание**: между запуском цикла и строкой `--- конец шага 2` нет ни одной строки `СОВПАДЕНИЕ:`; среди untracked-файлов нет Dockerfile'ов, entrypoint'ов и workflow'ов.
  **Провал**: любая строка `СОВПАДЕНИЕ: <файл>` — она сразу называет виновника; критичны прежде всего `docker-compose.yml`, `.github/workflows/ci.yml` (CI осознанно остаётся на `--all-packages` с dev-группой), `Makefile`, чужие Dockerfile'ы. Совпадение в файле, который тестировщик считает легитимным, но которого нет в allow-list, — не молчаливое «ок»: фиксировать в результате кейса и эскалировать.
  **Шаг 3 — содержание диффа четырёх файлов**:
  ```bash
  git diff -- backend/Dockerfile backend/entrypoint.sh \
    services/siem-service/Dockerfile services/siem-service/entrypoint.sh
  grep -n 'build-system' backend/pyproject.toml services/siem-service/pyproject.toml || echo "build-system отсутствует — ok"
  ```
  Ожидание: в диффе — замена `--all-packages` на `--no-dev --package <пакет>` в обоих `uv sync` каждого Dockerfile, комментарий над кэш-слоем, `export UV_NO_SYNC=1` после `set -e` в обоих entrypoint'ах. Bind-mount'ы, cache-mount `/root/.cache/uv`, `COPY backend/pyproject.toml` с комментарием над ним и `ENV PATH="/app/.venv/bin:$PATH"` — нетронуты; команды `uv run` не переписаны. `[build-system]` в обоих `pyproject.toml` отсутствует.
  **Провал**: не все четыре файла тронуты; правка T2-природы вне скоупа (кроме оговорённого `conventions.md`); удалён любой bind-mount или `COPY` pyproject'ов членов workspace; появился `[build-system]` (смена virtual → packaged меняет модель сборки всего workspace — это эскалация, а не правка).

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [ ] **Полный стек на прод-образах поднимается и работает.** Кейс проверяет то, чего разовые `docker run` показать не могут: что урезанные образы действительно живут в связке — миграции применяются, сервисы стартуют, фронт отдаётся, межсервисный обмен цел. `docker compose` здесь уже разрешён: барьер INTEGRATION_TEST пройден, параллельных треков с testcontainers-БД больше нет.
  **Предусловие**: барьер пройден, стек не запущен, `.env` заполнен по `.env.example`. Сервис главного приложения в compose называется `app`, SIEM — `siem-service`. К моменту INTEGRATION_TEST трек T4 переводит SIEM-сервисы в профиль `siem`, поэтому для их подъёма нужен `COMPOSE_PROFILES=siem` (либо `--profile siem`); если проверяется прод-профиль без SIEM — SIEM-часть кейса помечается неприменимой с этой причиной, а не пропускается молча.
  **Команды** (образы обязательно пересобрать — иначе поднимется старый кэш):
  ```bash
  docker compose --profile siem build app siem-service
  COMPOSE_PROFILES=siem docker compose up -d
  docker compose ps
  docker compose logs app | head -50
  docker compose logs siem-service | head -50
  # порты публикуются как 127.0.0.1:${APP_PORT:-8000}:8000 и 127.0.0.1:${SIEM_PORT:-8001}:8001 —
  # при непустых APP_PORT/SIEM_PORT в .env хардкод 8000/8001 дал бы ложное «стек не поднялся»
  set -a; [ -f .env ] && . ./.env; set +a
  curl -sS -o /dev/null -w '%{http_code}\n' "http://localhost:${APP_PORT:-8000}/health"
  curl -sS -o /dev/null -w '%{http_code}\n' "http://localhost:${SIEM_PORT:-8001}/health"
  curl -sS -o /dev/null -w '%{http_code}\n' "http://localhost:${APP_PORT:-8000}/"
  docker compose exec app /app/.venv/bin/python -c "import pytest" ; echo "exit=$?"
  ```
  **Ожидание**: все контейнеры в `Up`; в логах обоих сервисов — успешное применение миграций и старт uvicorn; health-эндпоинты и корень (SPA из `frontend/dist`) отвечают 2xx; последняя команда завершается **ненулевым** кодом (dev-группы нет и в запущенном контейнере, то есть `uv run` при старте её не вернул). В логах старта нет `Installed N packages` и имён dev-пакетов.
  **Провал**: любой контейнер не поднялся или рестартует; миграции не применились; `ModuleNotFoundError` на рантайм-зависимости (значит `--no-dev` срезал нужное — правка сломала прод); `import pytest` внутри работающего контейнера прошёл.
  **Примечание для тестировщика**: если стек падает по причине, не связанной с составом образов (отсутствующая переменная окружения, конфликт порта, чужой незакоммиченный код), — это не провал `{T2}`; зафиксировать причину и адресовать соответствующему треку.

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] 👤 **Приложение из прод-образа работает в браузере.** Открыть `http://localhost:${APP_PORT:-8000}` (SPA отдаётся backend-образом из `frontend/dist`, собранного стадией `frontend-build` того же Dockerfile), зарегистрироваться/залогиниться, отправить сообщение агенту и получить ответ. Кейс страхует от того, что урезанное окружение ломается не на старте, а на первом реальном запросе (SSE, LLM-вызов, запись в БД). **Провал**: 5xx, пустая страница, оборванный стрим при том, что стек по `{Layer 2}` считается поднятым.

---

## Находки ревью [severity+owner]

> Пишет **test-reviewer** (adversarial-ревью тестов против контракта, read-only). Каждая находка —
> severity (**blocker** / **major** / **minor**) + владелец фикса: `[test]` (test-author) /
> `[prod]` (fixer) / `[infra]` (`packages/testing`) / `[doc]`. На фазе GREEN fixer чинит `[prod]`,
> test-author — `[test]`; закрытую/эскалированную находку помечают здесь же. Чисто — секция пустая.

- **R1 major [test]** `{T2.4}` / `{T2.10}`, прогон под `--network none` — критерий провала недостижим, шаг вакуозен. Cache-mount `/root/.cache/uv` в слои образа не попадает, поэтому в контейнере колеса dev-группы взять неоткуда: без `UV_NO_SYNC` `uv run` упадёт на сетевой ошибке, а не напечатает `Installed N packages`, и кейс это падение засчитывает («конкретная ошибка неважна»). Шаг проходит одинаково с экспортом и без него; единственный дискриминатор эффекта на Layer 1 — «опциональный негативный контроль», а у `{T2.10}` его нет вовсе. → Сделать негативный контроль обязательным в обоих кейсах (он корректен: WORKDIR `/app`, корневой `learnflow-ai` держит `pytest` в dev-группе — `pyproject.toml:7-19`, — поэтому `uv run python -c "import pytest"` проходит ровно тогда, когда синк случился) **либо** прогонять контейнер с сетью, чтобы отсутствие экспорта реально дало `Installed N packages`. `grep` оставить: он честно закрывает требование брифа «`UV_NO_SYNC=1` в обоих entrypoint».
  **Закрыто (test-author, GREEN попытка 1):** `{T2.4}` и `{T2.10}` перестроены в три обязательных шага — A `grep UV_NO_SYNC` (требование брифа), B негативный контроль `--entrypoint uv … run python -c "import pytest"` **с сетью**, который обязан пройти с кодом 0 и напечатать установку (доказывает, что пересинк в этом образе реален), C целевой прогон entrypoint'а при тех же условиях с критерием «нет `Installed N packages` и dev-имён». `--network none` понижен до необязательного дополнительного прогона. Нет сети → кейс deferred, не «пройден». Метки *(исполнен при IMPLEMENT)* переписаны: шаг B implementer'ом не выполнялся, засчитать по summary нельзя.
- **R2 minor [test]** `{T2.3}` / `{T2.8}`, must-fail-цикл — `>/dev/null 2>&1` глотает любую причину ненулевого кода: опечатка в теге, неверный путь интерпретатора, неподнявшийся образ дадут `ok: … absent` по всем строкам разом (false-green всего кейса). Предусловие названо только `{T2.1}` / `{T2.6}` — сборка, но не работоспособность шва. → Добавить в предусловия `{T2.2}` / `{T2.7}` как позитивный контроль на том же абсолютном пути `/app/.venv/bin/python`, либо вкатить в цикл контрольную строку (`import sys` обязан пройти).
  **Закрыто:** в `{T2.3}` / `{T2.8}` добавлена контрольная строка перед циклом (`import uvicorn` на том же абсолютном пути обязан пройти, иначе `CONTROL FAILED` — кейс не засчитывать), а в предусловия добавлены `{T2.2}` / `{T2.7}` как позитивный контроль шва. `CONTROL FAILED` внесён в критерий провала обоих кейсов.
- **R3 minor [test]** `{T2.11}`, критерий (б) «**заметно** меньше» — не квантифицирован, в отличие от «строго меньше» в `{T2.5}`. Частичная правка (`--no-dev` без `--package`) кэш-слой тоже уменьшает, и «заметно» её пропустит. → Задать порядок: у implementer'а 268MB → 65.3MB (≥×3); плюс явно написать, что «`--no-dev` в одиночку» отсекается критерием (а), а не размером.
  **Закрыто:** критерий (б) `{T2.11}` квантифицирован — сокращение кэш-слоя **не менее чем в 3 раза** (ориентир implementer'а 268MB → 65.3MB ≈ ×4,1); в провал добавлена строка «сокращение есть, но меньше трёхкратного» с указанием типичной причины (`--no-dev` без `--package`) и явной оговоркой, что этот случай ловится в первую очередь критерием (а) — по отсутствию `--package` в тексте слоя.
- **R4 minor [test]** `{T2.12}`, метка *(исполнен при IMPLEMENT)* — единственный кейс с нулевой стоимостью перепрогона (три read-only git-команды) засчитывается по `git status` самого автора правок; проверка собственных границ автором изменения — ровно та тавтология, против которой стоит A6 (`testing.md` § Целостность тестов). → Снять метку с `{T2.12}` либо явно предписать перепрогон тестировщиком.
  **Закрыто:** метка *(исполнен при IMPLEMENT)* с `{T2.12}` снята, кейс начинается с явного «исполняет тестировщик, засчитывать по summary нельзя» со ссылкой на A6. Проверка переписана в три исполняемых шага: сверка явного списка четырёх файлов трека с `git diff --name-only HEAD` через `comm` (оба направления), grep по диффу **остальных** изменённых файлов на маркеры T2-природы (`uv sync`, `UV_NO_SYNC`, `--all-packages`, `--no-dev`) с единственным допустимым исключением `doc/tech/conventions.md` (зона T1), затем разбор диффа четвёрки и проверка отсутствия `[build-system]`.
- **R5 minor [test]** Layer 2, порты — `curl localhost:8000` / `8001` захардкожены, а compose публикует `127.0.0.1:${APP_PORT:-8000}:8000` и `127.0.0.1:${SIEM_PORT:-8001}:8001` (`docker-compose.yml:47-48`, `:133-134`). При непустых `APP_PORT`/`SIEM_PORT` в `.env` шаг упадёт и прочитается как «стек не поднялся». → Записать порт как `${APP_PORT:-8000}` / `${SIEM_PORT:-8001}`.
  **Закрыто:** порты Layer 2 параметризованы — `${APP_PORT:-8000}` / `${SIEM_PORT:-8001}` с подгрузкой `.env` перед `curl`; Layer 3 👤 тоже переведён на `${APP_PORT:-8000}`. В команды добавлен комментарий с реальными строками публикации портов.
- **R6 minor [doc]** `summary.md:64` § Follow-ups пуста, хотя `plan.md:231` (Open Question #1, ЗАКРЫТ) обязывает передать наблюдение «исходники и тесты в прод-образе» в backlog именно через эту секцию → harvester. Передача потеряна, а наблюдение в силе: `backend/Dockerfile:38-40` тащит `backend/` целиком (включая `tests/`) и `services/`, `services/siem-service/Dockerfile:31-32` — `packages/` и `services/`. → Вписать follow-up (P3, «тестовый и чужой код в прод-образе») в summary трека. Владелец — автор summary, не test-author.
- **R7 minor [test]** § Дизайн автотестов, буллет про стража `--all-packages` — утверждает, что `{T2.5}`/`{T2.11}` «проверяют эффект в собранном образе», тогда как критерий (а) обоих кейсов сам текстовый (сверка `CreatedBy` в `docker history`). Держать его стоит — бриф § 4 предписывает именно `--no-dev` + `--package`, так что это контракт, а не enshrine реализации, — но подавать как effect-based нельзя: эквивалентная запись (`ENV UV_NO_DEV=1` + `--package`) критерий (а) провалит, и это повод эскалировать, а не «починить» кейс. → Переформулировать буллет: (а) — текстовая сверка контрактных флагов, (б) — эффект.
  **Закрыто:** буллет в § Дизайн автотестов переформулирован — (а) названо текстовой сверкой **контрактных** флагов из брифа § 4 по `CreatedBy` слоёв (не эффектом и не enshrine реализации), (б) — эффектом (размер слоя). Добавлено следствие для тестировщика: эквивалентная запись (`ENV UV_NO_DEV=1`) провалит (а) при выполненном (б) — это эскалация расхождения с брифом, а не правка кейса. То же следствие продублировано в критериях `{T2.5}` и `{T2.11}`.
- **R8 nit [test]** `{T2.7}`, позитивный список — нет `fastapi` и `pydantic_settings`, хотя оба в `[project.dependencies]` siem (`services/siem-service/pyproject.toml:7,14`), а в парном `{T2.2}` `fastapi` проверяется. Пробел закрыт косвенно листингом `/app/.venv/bin` в `{T2.8}`. → Добавить для симметрии.
  **Закрыто:** в позитивный список `{T2.7}` добавлены `fastapi` и `pydantic_settings` — симметрично `{T2.2}`.

**Re-glance закрытий (test-reviewer, после GREEN попытки 1).** Проверялись точечно R1 и R4.

**R1 — закрыто.** Цепочка A→B→C сходится: B доказывает, что индекс достижим и uv в этом образе физически может доставить dev-группу, поэтому «чисто» в C перестало быть неотличимым от «не смог». Дискриминация подтверждается формой вызовов: без `UV_NO_SYNC` первая команда backend-entrypoint'а (`uv run alembic …` из WORKDIR `/app`, `backend/entrypoint.sh:9`) — ровно та же форма, что в шаге B (корневой проект, без `--package`), то есть напечатала бы `Installed N packages` до падения; у siem первая команда — `uv run --package siem-service alembic …` (`services/siem-service/entrypoint.sh:9`), и её dev-группа (`learnflow-testing` → `pytest`, `services/siem-service/pyproject.toml:38-42`) тоже поехала бы в установку. Ложного зелёного в B не нашёл: пройти он может только если `pytest` уже лежит в `/app/.venv`, а это состояние ловит `{T2.3}`/`{T2.8}`; в backend-версии дырка закрыта прямо в ожидании («в выводе видна установка `Installed N packages`»). Два хвоста ниже.

- **R9 nit [test]** `{T2.10}` шаг B — ожидание требует только «код 0 и `resync happened`», без свидетельства установки, тогда как парный `{T2.4}` требует `Installed N packages`. Если `pytest` окажется в образе (то есть при уже провалившемся `{T2.8}`), B пройдёт вакуозно. → Добавить требование `Installed N packages` в ожидание `{T2.10}` шага B и/или внести `{T2.8}` в предусловия (в `{T2.4}` — `{T2.3}`).
  **Закрыто (test-author, fix-цикл 2):** в ожидание шага B `{T2.10}` внесено третье обязательное свидетельство — `Installed N packages` в выводе; явно записано, что успешный импорт без строки установки означает провал `{T2.8}`, а не успех контроля. В предусловия `{T2.10}` добавлен `{T2.8}`, в предусловия `{T2.4}` — `{T2.3}` (симметрично).
- **R10 nit [test]** `{T2.10}` шаг B зовёт `uv run` без `--package`, а реальный siem-entrypoint — `uv run --package siem-service`. Как контроль «сеть/индекс/шов работают» это годится, но точным зеркалом шага C не является. → Сильнее: `uv run --package siem-service python -c "import pytest; print('resync happened')"` — валидно, `pytest` приходит в siem через `learnflow-testing` в его dev-группе.
  **Закрыто:** шаг B `{T2.10}` приведён к зеркалу шага C — `uv run --package siem-service python -c "import pytest; …"` (dev-группа `siem-service` тянет `learnflow-testing` → `pytest`), проверяется тот же путь резолвинга, что у настоящего entrypoint'а. Заодно в `{T2.4}` оговорено, почему там форма без `--package` корректна: она зеркалит первый `uv run` backend-entrypoint'а (`uv run alembic …`, тоже без `--package`).

**R4 — закрыто частично.** Шаги 1 и 3 исполнимы и корректны, прогнал на текущем worktree: `comm -12` даёт ровно четыре файла скоупа, `comm -13` пуст, сортировка обоих списков одним `sort` требование `comm` соблюдает; `grep -n 'build-system'` по обоим `pyproject.toml` отрабатывает. Шаг 2 в текущем виде даёт **ложный красный** и не атрибутирует находки — детали ниже.

- **R11 minor [test]** `{T2.12}` шаг 2 — прогон на этом worktree выдаёт четыре совпадения, из них два в `doc/tasks/.../design-brief.md` (строки партиции и § 4 цитируют `uv sync --locked --all-packages`) и два в `doc/tech/conventions.md`. По букве критерия («любой другой файл в выводе — провал») кейс валится, хотя нарушения нет: бриф — артефакт архитектора, а не правка T2. → Расширить allow-list на документы итерации (`doc/tasks/iterations/**`, `doc/tech/conventions.md`), сформулировав его как «правки T2-природы в **сборочных** файлах», а не «любое упоминание флагов».
  **Закрыто:** критерий шага 2 переформулирован с «упоминание флагов в любом файле» на «правки T2-природы в **сборочных** файлах» (Dockerfile, entrypoint, compose, CI-workflow, Makefile), добавлен allow-list `doc/tasks/iterations/*` и `doc/tech/conventions.md` с объяснением, почему цитаты в брифе и правка T1 нарушением не являются. Совпадение в файле вне allow-list, который тестировщик считает легитимным, предписано фиксировать и эскалировать, а не пропускать.
- **R12 minor [test]** `{T2.12}` шаг 2 — вывод `git diff … | grep -nE …` печатает номера строк сплошного диффа без имени файла, так что отличить `conventions.md` от `design-brief.md` (и от реального нарушения) по нему нельзя; вердикт кейса становится неисполнимым. Плюс `$TMP` наследуется из шага 1 — при запуске блоков в разных сессиях подстановка `$(… | grep -vFf "$TMP/t2-scope.txt")` схлопнется в пустой список и `git diff --` покажет **все** файлы, включая четвёрку скоупа. → Переписать шаг пофайловым циклом с печатью имени, например `for f in $(git diff --name-only HEAD | grep -vxFf "$TMP/t2-scope.txt"); do git diff -- "$f" | grep -qE '<маркеры>' && echo "СОВПАДЕНИЕ: $f"; done`, и сделать блок самодостаточным (свой `TMP=`/`printf`). Заодно `-vFf` → `-vxFf`: без `-x` фильтр отсекает и пути, куда список скоупа входит подстрокой.
  **Закрыто:** шаг 2 переписан самодостаточным пофайловым циклом (`for f in $(git diff --name-only HEAD | grep -vxFf …)`) с печатью `СОВПАДЕНИЕ: <файл>` — виновник называется по имени; блок заново заводит свой `TMP=`/`printf`, поэтому не зависит от шага 1; `-vFf` заменён на `-vxFf` с явным пояснением. Добавлена строка-терминатор `--- конец шага 2` и проверка untracked-файлов на сборочные. Блок прогнан на текущем worktree: ложных срабатываний нет, вывод чистый.

**Чисто:** baseline-рецепт `{T2.5}`/`{T2.11}` исполним как написан — `git log -1 --format=%H -- <Dockerfile>` даёт `113649e` (правки трека не закоммичены), `git show` отдаёт до-трековый файл, `grep -c -- '--all-packages'` = 2 в обоих файлах; ветка-фолбэк на `sed -n 2p` синтаксически верна. Дискриминатор кэш-слоя работает: BuildKit пишет в `CreatedBy` shell-команду без `--mount`-флагов, но с `--no-install-workspace` (проверено на `learnflow-ai-siem-service:latest`: `248MB RUN /bin/sh -c uv sync --locked --no-install-workspace --all-packages # buildkit`). Обоснование отказа от `import app` / `import siem_service` верно — ни у `backend/pyproject.toml`, ни у `services/siem-service/pyproject.toml` нет `[build-system]`; при этом у `packages/testing/pyproject.toml` он есть, поэтому `import learnflow_testing` в `{T2.3}`/`{T2.8}` — валидная негативная проверка. `asyncpg` как дискриминатор `--package` корректен (есть только в зависимостях siem, `services/siem-service/pyproject.toml:10`; в `backend/pyproject.toml` отсутствует). `{T2.9}` соответствует `services/siem-service/Dockerfile:39` — в `/app/backend` кладётся ровно `pyproject.toml`. Порядок аргументов `--entrypoint grep|ls <tag> …` валиден, `grep` в slim-образе есть. `UV_NO_SYNC` — документированный env `uv run` (`--no-sync … [env: UV_NO_SYNC=]`, uv 0.11.26). Заявление о расхождении с CI точно: `.github/workflows/ci.yml:33` — `uv sync --all-packages`; `doc/tech/conventions.md:124` уже несёт правило `--no-dev --package` (зона T1, треком не тронута). Все 12 ссылок *(исполнен при IMPLEMENT)* указывают на реальные строки `summary.md` § Verification / § Размеры. Cross-cutting Layer 2 сверен с кодом: сервисы называются `app` и `siem-service`, `/health` есть у обоих (`backend/app/main.py:684`, `services/siem-service/siem_service/main.py:146`), SPA на `/` отдаётся (`main.py:714-731`, `parents[2]` = `/app` → `/app/frontend/dist`, совпадает с `backend/Dockerfile:52`), явного `image:` у сборочных сервисов нет — теги `t2-*` ни с чем не столкнутся. Прод-багов в четырёх файлах трека нет: дифф ровно по плану, bind-/cache-mount'ы, `COPY backend/pyproject.toml`, `ENV PATH` и команды `uv run` не тронуты. Операционная заметка тестировщику: образов `t2-before`/`t2-after` implementer'а в локальном демоне больше нет, любой перепрогон `{T2.2}`–`{T2.5}` требует полной пересборки backend-образа (и baseline'а — со стадией `frontend-build`).

---

## Покрытие

| Инвариант / риск из design-brief § 4 и плана | Закрывающие кейсы |
|---|---|
| Образы собираются после правки | `{T2.1}`, `{T2.6}` |
| Рантайм не сломан `--no-dev` (alembic, uvicorn, зависимости сервиса) | `{T2.2}`, `{T2.7}`, Layer 2 |
| Dev-группа (pytest/mypy/ruff/pre-commit/testcontainers/learnflow-testing) из образов ушла | `{T2.3}`, `{T2.8}`, Layer 2 |
| `--package` работает как отбор члена workspace (чужие зависимости не заезжают) | `{T2.3}` (`asyncpg`), `{T2.8}` (LangChain-стек) |
| Код backend'а не попадает в siem-образ, но workspace-резолвер удовлетворён | `{T2.9}`, `{T2.6}` |
| `UV_NO_SYNC=1` не даёт `uv run` вернуть dev-группу при старте контейнера | `{T2.4}`, `{T2.10}`, Layer 2 |
| Правка затронула **оба** `uv sync` в каждом файле (иначе экономия мнимая) | `{T2.5}`, `{T2.11}` |
| Заявленная экономия размера реальна | `{T2.5}`, `{T2.11}` (слой), `{T2.1}`, `{T2.6}` (суммарно) |
| Файловый скоуп трека не превышен; virtual-члены не переведены в packaged | `{T2.12}` |
| Урезанные образы работают в связке, а не только по отдельности | Layer 2, Layer 3 👤 |
