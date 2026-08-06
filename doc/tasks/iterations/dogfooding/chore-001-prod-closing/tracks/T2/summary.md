# Summary: трек T2 — прод-образы без dev-зависимостей

## TL;DR

Трек T2 закрыт целиком: оба прод-образа (`backend`, `siem-service`) больше не тянут dev-группу (pytest, mypy, ruff, testcontainers и т. д.) и лишних членов workspace — все четыре вызова `uv sync` (по два на образ) синкают только рантайм-зависимости своего пакета. Оба `entrypoint.sh` заблокированы от пересинка окружения при старте контейнера через `UV_NO_SYNC=1`. У backend-образа кэш-слой похудел с 268MB до 145MB, суммарный размер — с 842MB до 719MB. У siem-образа эффект больше: `--package siem-service` дополнительно вымел из образа весь чужой LangChain/LangGraph/Langfuse/psycopg-стек backend'а, кэш-слой упал с 268MB до 65.3MB, суммарный размер образа — с 459MB до 256MB. Верификация пройдена по всем пунктам обеих фаз.

## Что реализовано (T2.1)

`backend/Dockerfile`: в кэш-слое (было `uv sync --locked --no-install-workspace --all-packages`) и в финальном слое «Install project» (было `uv sync --locked --all-packages`) флаг `--all-packages` заменён на пару `--no-dev --package learnflow-backend`. Bind-mount'ы pyproject.toml всех членов workspace и cache-mount `/root/.cache/uv` остались нетронутыми — они нужны резолверу uv независимо от того, какой пакет ставится. Над кэш-слоем добавлен комментарий, фиксирующий, что прод-образ осознанно расходится с CI (там `--all-packages` с dev-группой — сам инструментарий и есть цель), и что оба вызова `uv sync` обязаны нести одинаковые флаги: то, что установил кэш-слой, физически остаётся в образе даже если финальный sync это подрежет.

`backend/entrypoint.sh`: сразу после `set -e` добавлен `export UV_NO_SYNC=1` с комментарием — без него `uv run` при старте контейнера пересинканул бы окружение и вернул dev-группу обратно. Команды `uv run alembic … upgrade head` и `uv run --package learnflow-backend uvicorn …` не менялись.

Изменены ровно два файла: `backend/Dockerfile`, `backend/entrypoint.sh` (`git status` подтверждён — остальные изменения в worktree принадлежат параллельному треку T1).

## Что реализовано (T2.2)

`services/siem-service/Dockerfile`: та же пара правок, что в T2.1, применена к своему пакету — в кэш-слое (было `uv sync --locked --no-install-workspace --all-packages`) и в финальном слое «Install project» (было `uv sync --locked --all-packages`) флаг `--all-packages` заменён на пару `--no-dev --package siem-service`. Комментарий над кэш-слоем — по образцу T2.1, с дополнением: `--package` здесь не только убирает dev-группу, но и отсекает от образа весь чужой стек backend'а (LangChain/LangGraph/Langfuse/psycopg), который раньше заезжал через `--all-packages`, хотя код backend'а в образ не копируется вовсе. `COPY backend/pyproject.toml /app/backend/pyproject.toml` и комментарий над ним (объясняющий, зачем в virtual-workspace-образ попадает чужой pyproject без исходников) оставлены дословно — они верны независимо от флага `--package`, это требование workspace-резолвера uv. `ENV PATH="/app/.venv/bin:$PATH"` не тронут.

`services/siem-service/entrypoint.sh`: сразу после `set -e` добавлен `export UV_NO_SYNC=1` с тем же комментарием, что в T2.1. Команды `uv run --package siem-service alembic upgrade head` и `uv run --package siem-service uvicorn …` не менялись.

Изменены ровно два файла в скоупе фазы: `services/siem-service/Dockerfile`, `services/siem-service/entrypoint.sh` (`git status` подтверждён — прочие изменения в worktree принадлежат параллельным трекам T1/T3/T4).

## Решения и обоснования

Правка обоих вызовов `uv sync`, а не только финального, обязательна из-за кумулятивности docker-слоёв: `uv sync` по умолчанию exact и «удаляет» лишнее из финального venv, но файлы, записанные более ранним RUN-слоем, остаются в образе под whiteout — реального выигрыша в размере и pull-трафике без правки кэш-слоя не будет. Это подтвердилось на практике: суммарный размер образа снизился умеренно (842MB → 719MB), а конкретный RUN-слой кэша — почти вдвое (268MB → 145MB), что и было заявленным в плане дискриминатором между «поправлен один вызов» и «поправлены оба».

`--package learnflow-backend` без `--no-dev` цели не достиг бы: dev-зависимости `learnflow-backend` (pytest, testcontainers, learnflow-testing и т. д.) объявлены в собственной dev-группе пакета, а не в корневой, и `--no-dev` без `--package` их бы тоже не убрал по той же причине в обратную сторону.

`UV_NO_SYNC=1` — задокументированный флаг `uv run` (не недокументированный трюк), выключающий implicit re-sync окружения при каждом вызове `uv run` в контейнере; без него рантайм-образ восстанавливал бы dev-группу при первом же старте, сводя на нет всю экономию сборки.

Для siem-образа `--package siem-service` даёт заметно больший эффект, чем для backend: до правки `uv sync --all-packages` тянул в этот образ весь workspace целиком, включая члена `learnflow-backend` с его LangChain/LangGraph/Langfuse/psycopg-зависимостями — код backend'а туда даже не копируется, дистрибутивы лежали в `.venv` мёртвым грузом и поверхностью атаки. Это видно и по абсолютным цифрам: у backend-образа кэш-слой сократился на 123MB (268MB → 145MB), у siem-образа — на 203MB (268MB → 65.3MB) при одинаковом стартовом размере слоя, потому что backend и так остаётся «хозяином» львиной доли зависимостей, а у siem всё лишнее было полностью чужим.

`siem_service` и `app` (virtual-члены workspace `services/siem-service` и `backend`) сознательно не фигурируют в верификации ни как позитивная, ни как негативная проверка: у обоих `source = { virtual = … }` в `uv.lock`, и без `[build-system]` в их `pyproject.toml` uv не устанавливает их в `.venv` — ни до правки, ни после. Дырку, которую не проверяет импорт, закрывает шаг `ls /app/backend` (ожидается ровно `pyproject.toml`, то есть код backend'а в образ не заехал).

## Verification — результаты (T2.1)

| Шаг плана | Результат |
|---|---|
| 1. Рантайм цел (`import uvicorn, alembic, fastapi, langgraph, langfuse, psycopg, redis, siem_contracts`; `alembic --version`; `uvicorn --version`) | exit 0 во всех трёх случаях |
| 2. Dev-зависимостей нет (`pytest`, `_pytest`, `testcontainers`, `learnflow_testing`, `factory`, `mypy`) + `asyncpg` (чужая зависимость siem-service) | все шесть плюс `asyncpg` отсутствуют; в `/app/.venv/bin` нет `pytest`, `ruff`, `mypy`, `pre-commit`, `lint-imports` |
| 3. Entrypoint не пересинкает окружение (`grep UV_NO_SYNC`; прогон под `--network none`) | `UV_NO_SYNC=1` найден в `/app/entrypoint.sh`; прогон дал `Running database migrations...`, затем ValidationError на отсутствующем `jwt_secret` (валидация Settings) — в выводе нет `Installed N packages` и нет имён dev-пакетов; строки `Resolved N packages` не было вовсе (офлайн-сверка lock прошла тихо, что тоже допустимо по критерию) |
| 4. Кэш-слой похудел (`docker history`) | слой `uv sync … --no-install-workspace --package learnflow-backend`: 268MB (before) → 145MB (after), строго меньше |
| 5. `git status` — изменены ровно два файла | подтверждено; прочие изменения в worktree — от параллельного трека T1, не затронуты |

## Verification — результаты (T2.2)

| Шаг плана | Результат |
|---|---|
| 1. Рантайм цел (`import uvicorn, alembic, asyncpg, sqlalchemy, redis, structlog, jwt, siem_contracts`; `alembic --version`) | exit 0 в обоих случаях |
| 2. Backend-стека и dev-группы нет (`langgraph`, `langchain`, `langchain_core`, `langfuse`, `psycopg`, `pytest`, `testcontainers`, `learnflow_testing`) + `ls /app/backend` | все восемь модулей отсутствуют; в `/app/.venv/bin` нет ничего из dev/backend-инструментария (только `alembic`, `dotenv`, `fastapi`, `mako-render`, `python*`, `uvicorn`, `watchfiles`, `websockets`, `activate*`); `/app/backend` содержит ровно одну запись — `pyproject.toml` |
| 3. Entrypoint не пересинкает окружение (`grep UV_NO_SYNC`; прогон под `--network none`) | `UV_NO_SYNC=1` найден в `/app/entrypoint.sh`; прогон дал `Running siem-service database migrations...`, затем `ConnectionRefusedError` на недоступной БД — в выводе нет ни `Installed N packages`, ни `Resolved N packages`, ни имён dev-пакетов |
| 4. Кэш-слой похудел (`docker history`) | слой `uv sync … --no-install-workspace --package siem-service`: 268MB (before) → 65.3MB (after), строго меньше |
| 5. `git status` — изменены ровно два файла в скоупе фазы | подтверждено; прочие изменения в worktree — от параллельных треков T1/T3/T4, не затронуты |

### Размеры

| Образ | До | После | Дельта |
|---|---|---|---|
| `learnflow-backend` (суммарно) | 842MB | 719MB | −123MB |
| RUN-слой кэша backend (`uv sync … --no-install-workspace …`) | 268MB | 145MB | −123MB |
| `siem-service` (суммарно) | 459MB | 256MB | −203MB |
| RUN-слой кэша siem (`uv sync … --no-install-workspace --package siem-service`) | 268MB | 65.3MB | −202.7MB |

## Follow-ups

## SOFA-посты (id / применил / результат)
