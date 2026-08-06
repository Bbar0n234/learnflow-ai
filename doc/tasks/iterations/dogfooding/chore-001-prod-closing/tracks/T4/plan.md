# Implementation Plan: chore-001 / трек T4 — SIEM kill-switch

## Контекст

Трек выключает SIEM в проде, не удаляя ни строчки его кода. Выключение распадается на три слоя, потому что исполняют их три разные системы и ни одна не видит переменные другой: python-процесс приложения перестаёт эмитить события в Redis Stream (`SIEM_ENABLED`), docker compose перестаёт поднимать и собирать `siem-service`/`siem-db` (`COMPOSE_PROFILES` + `profiles:`), а сборка фронта выбрасывает роут `/security` и кнопку «Безопасность» (build-time `VITE_SIEM_ENABLED`). Дефолты — «включено», поэтому dev ведёт себя как сейчас, а прод гасит подсистему явными строками в `.env`. Довеском трек чинит два дрейфа, вскрытых при чтении кода (`VITE_SIEM_API_URL` в `.env.example`, пути REST в `siem-service.md`), и дописывает в прод-runbook секцию с последовательностью ручных шагов на VM.

Источники:

- Запись итерации: [tasklist-dogfooding.md](../../../../../tasklist-dogfooding.md) § chore-001 (B) — пункт backlog «SIEM kill-switch» (P2, вариант A).
- Design-brief: [design-brief.md](../../design-brief.md) § 2 «SIEM kill-switch», § «Env-гигиена», § «Ручные шаги на прод-VM», § «Сопутствующие правки», § «Партиция треков» (строка T4).
- Конвенции: [conventions.md](../../../../../../tech/conventions.md) § Конфигурация через env-файлы (правило четырёх мест), § Module-level state, § Logging Conventions, § Documentation; [conventions/frontend.md](../../../../../../tech/conventions/frontend.md) § фиче-флаги (`shared/config/feature-flags.ts`).
- Смежные документы: [siem-service.md](../../../../../../tech/siem-service.md), [setup/production.md](../../../../../../tech/setup/production.md) (создан T1, дополняется здесь).
- Предшествующие треки: [T1/plan.md](../T1/plan.md) (форма env-файлов, каркас runbook'а), [T3/summary.md](../T3/summary.md) (форма kill-switch'а и INFO-лога), [T2/plan.md](../T2/plan.md) (`backend/Dockerfile` уже приведён к `--no-dev --package`).

**Границы трека** (по § Партиция треков): `backend/app/main.py` (только блок создания transport + `publisher_loop`), `backend/app/config.py` (только `SIEM_ENABLED`), `docker-compose.yml` (profiles, `build.args`, env-строка), `backend/Dockerfile` (только стадия `frontend-build`), `frontend/src/shared/config/feature-flags.ts`, `frontend/src/app/router.tsx`, `frontend/src/app/components/Sidebar.tsx`, `.env.example`, `.env.local.example`, `doc/tech/siem-service.md`, `doc/tech/setup/production.md`. Тест-скоуп — новая директория `backend/tests/siem_toggle/` и Vitest-колокация во фронте; наполняет их `test-author` отдельно, implementer тестов не пишет.

Явно **не** входит: код SIEM (`services/siem-service/`), вокабуляр `packages/siem-contracts` (сверено — не меняется), продьюсеры событий (`auth.py`, `guard.py`), structlog-процессор, `RedisEventTransport`, Redis как таковой, volume `siem_pgdata`, arch-checker/import-linter, CI.

## Согласованные факты по коду (сверено с реализацией)

**Слой 1 — эмиссия.**

- `backend/app/main.py:269-270` создаёт `EventTransportHolder()` и кладёт его в `app.state`; `:275` передаёт холдер в `make_security_event_processor(...)` при `setup_logging`. Холдер и процессор создаются **до** Redis и под флаг не уходят — процессор остаётся в цепочке structlog всегда.
- `backend/app/main.py:324-334`: `app.state.redis = await create_redis(settings)`, затем `if app.state.redis is not None:` → `RedisEventTransport(...)`, `transport_holder.set(...)`, `asyncio.create_task(event_transport.publisher_loop())`, `logger.info("security event publisher started")`. Это единственная точка врезки слоя 1.
- `backend/app/security_pipeline/processor.py:130-132`: `transport = holder.get()`; `if transport is not None: transport.put_nowait(...)`. Пустой холдер = молчаливый дроп, правок в процессоре не требуется.
- Shutdown (`main.py:630-638`) обёрнут в `if hasattr(app.state, "security_publisher_task")` — при несозданной задаче блок целиком пропускается, правок не требуется.
- `create_redis` остаётся безусловным: тот же клиент питает `TraceStore` (`deps.py`, `routes/feedback.py`, `services/chat.py`) — отключать Redis нельзя.
- SIEM-тесты `backend/tests/security/test_event_processor.py` и `test_event_transport.py` не упоминают ни `lifespan`, ни `create_app` (grep) — правка слоя 1 их, по всей видимости, не заденет.

**Env.**

- `backend/app/config.py` — плоский `BaseSettings` без `env_prefix`, секции разделены комментариями; `llm_defense_enabled` (T3) живёт в секции `# Security (prompt injection protection)`, Redis — в `# Redis (trace storage for feedback persistence)` (`:48-49`).
- **Коллизии имён нет** — проверено эмпирически: `siem_service.config.Settings` (`env_prefix="SIEM_"`, `extra='forbid'` по умолчанию pydantic-settings) конструируется без ошибок при `SIEM_ENABLED=false` в окружении. Это существенно, потому что `LOAD_ENV` в Makefile сорсит `.env`/`.env.local` в шелл целиком, и переменная видна процессу siem-service при локальном запуске.
- Форма `.env.local.example` для тумблеров, закреплённая T1 и T3: закомментированная строка с пометкой, что дефолт совпадает с системным (строки 8-12 файла).

**Слой 2 — контейнеры.**

- `docker-compose.yml`: `siem-db` — `:106-127`, `siem-service` — `:129-166`; `volumes:` объявляет `siem_pgdata` на `:177`. У `app.build` (`:43-45`) секции `args:` сегодня нет.
- **`COMPOSE_PROFILES` из `.env` работает** — проверено на одноразовом проекте и на копии реального `docker-compose.yml` с наложенными правками: `docker compose config --services` при `COMPOSE_PROFILES=siem` даёт `db redis app siem-db siem-service`, без переменной — `db redis app`. Сети команда не требует (важно: docker-сеть на машине сейчас сломана).
- **`docker compose` не читает `.env.local`** — проверено там же: `COMPOSE_PROFILES` в `.env.local` профиль не активирует. `make docker-up` — это голый `docker compose up -d` без `LOAD_ENV`, то есть источник только `.env`.
- Профили опциональны по устройству compose: «профиль по умолчанию включён» выразить нельзя. Следствие для dev описано в Cross-cutting.

**Слой 3 — UI.**

- `frontend/src/shared/config/feature-flags.ts` — единственный существующий флаг `SHOW_GROUP_B_STUBS`, импортируется прямым путём `@/shared/config/feature-flags` (barrel'а в `shared/config/` нет). Канон зафиксирован в `conventions/frontend.md:47`.
- `frontend/src/app/router.tsx`: `:13` — статический импорт `SecurityRouteGuard`, `:16-20` — `lazy` для `SecurityPage`, `:34-43` — сам `<Route path="security">`.
- `frontend/src/app/components/Sidebar.tsx:96-106` — кнопка «Безопасность» уже под условием `isAdmin`.
- `frontend/src/shared/api/security.ts:89` — образец паттерна: `import.meta.env.VITE_SIEM_API_URL ?? "/siem/api"`.
- `make dev-fe` — `cd frontend && npx vite`, файлов `frontend/.env*` в репозитории нет → `VITE_SIEM_ENABLED` не определена → срабатывает `?? "true"`, флаг включён.
- `backend/Dockerfile:1-7` — стадия `frontend-build`, `RUN npm run build` на `:7`; `ARG`/`ENV` в стадии сегодня нет. Оба `uv sync` уже несут `--no-dev --package` (T2 завершён) — трогать их не нужно.
- Проверено на копии compose: `build.args.VITE_SIEM_ENABLED: ${SIEM_ENABLED:-true}` рендерится в `"false"` при `SIEM_ENABLED=false` в `.env` и в `"true"` без неё.

**Сопутствующие правки.**

- `services/siem-service/siem_service/api/routes.py:26` — `APIRouter(prefix="/api/security")`. В `doc/tech/siem-service.md:149-156` восемь строк таблицы REST перечислены без префикса `/api` — дрейф.
- `.env.example:116` — `VITE_SIEM_API_URL=http://localhost:8001/siem/api`. Дефолт во фронте (`/siem/api`) для прода верен: nginx срезает префикс через `location /siem/` + `proxy_pass ...:8001/` (референс в `production.md`). Сломан именно dev-пример, где nginx нет.
- `doc/tech/setup/production.md` — `## Runbook ручных шагов на прод-VM` (`:109`) с подзаголовком `### Клиентский IP` (`:115`) и прямой оговоркой «шаги новых подсистем добавляются как отдельные подзаголовки, не переписывая существующие». Слот под T4 подготовлен.

---

## Фазы

### T4.1: Env-поверхность — `SIEM_ENABLED` в четырёх местах

**Цель:** завести операционный тумблер эмиссии до того, как появится читающий его код, — по форме, отработанной T1 и T3.

**Изменения:**

- `backend/app/config.py` — `siem_enabled: bool = True` в **собственной** секции-комментарии (например `# SIEM (security event emission)`), рядом с блоком Redis, а не внутри `# Security (prompt injection protection)`: тумблер относится к пайплайну security-событий, а не к защите от prompt injection, и смешивать их в одной секции — ложный сигнал читателю. Комментарий из двух предложений (форма T3): что гасит (только эмиссию событий в Redis Stream из этого процесса) и чего не гасит (контейнеры — `COMPOSE_PROFILES`, UI — `VITE_SIEM_ENABLED`), плюс что читается один раз в lifespan.
- `.env.example` — `SIEM_ENABLED=true` в блоке `# ───────── SIEM service ─────────` (`:67`), первой строкой блока: это операционный тумблер всей подсистемы, остальные `SIEM_*` — её настройки. Комментарий: дефолт `true` (dev как сейчас), прод ставит `false`; переключение требует рестарта контейнера; выключает **только** эмиссию — контейнеры гасит `COMPOSE_PROFILES` (появится в T4.3), UI — `VITE_SIEM_ENABLED` (T4.5).
- `.env.local.example` — закомментированная строка `# SIEM_ENABLED=true` в SIEM-блоке (`:17-25`) с пометкой, что дефолт совпадает с системным и переопределение для local dev не требуется.
- `docker-compose.yml` — `SIEM_ENABLED: ${SIEM_ENABLED:-true}` в `environment:` сервиса `app`, рядом с `REDIS_URL`/`LLM_DEFENSE_ENABLED`, по одной переменной (без `env_file:`). В `siem-service` переменная **не** прокидывается: там `env_prefix="SIEM_"`, и `SIEM_ENABLED` отобразилась бы на несуществующее поле `enabled` — смысла ноль, а читателя вводит в заблуждение.

**Verification:**

- `make check` проходит.
- `Settings()` с пустым окружением даёт `siem_enabled is True`; при `SIEM_ENABLED=false` — `False`.
- Регрессия на коллизию префикса: `siem_service.config.Settings()` конструируется при `SIEM_ENABLED=false` в окружении (факт уже подтверждён, фаза не должна его потерять).
- `docker compose config` парсится; `SIEM_ENABLED` виден в отрендеренном окружении сервиса `app` и отсутствует у `siem-service`.
- Grep подтверждает наличие переменной в `config.py`, `.env.example`, `.env.local.example`, `docker-compose.yml` — правило четырёх мест выполнено.

---

### T4.2: Слой 1 — эмиссия событий под флагом

**Цель:** при `SIEM_ENABLED=false` не создавать ни transport, ни `publisher_loop`, оставив холдер пустым и всю остальную цепочку нетронутой.

**Изменения:**

- `backend/app/main.py`, блок `:326-334` — условие переписывается так, чтобы «выключено флагом» и «Redis недоступен» оставались **различимыми** ветками, а не схлопывались в одну:

  ```
  if not settings.siem_enabled:
      logger.info("siem event emission disabled by flag")
  elif app.state.redis is not None:
      ... как сейчас ...
  ```

  Это прямое требование brief § 1 «Принятые следствия» (последний пункт): молчаливая деградация запрещена, а сегодня оба состояния дают одинаково пустой холдер. Форма условия обязана давать **ровно одну** INFO-строку за старт и не эмитить её, когда флаг включён, а Redis лежит.
- Не трогаются: создание `EventTransportHolder()` и передача его в `make_security_event_processor` (`:269-275`) — процессор должен остаться в цепочке и молча дропать; `create_redis` — Redis нужен `TraceStore`; блок shutdown (`:630-638`) — уже защищён `hasattr`; `app.state.security_transport_holder` — по-прежнему выставляется всегда.
- Продьюсеры событий, `RedisEventTransport`, `processor.py` — вне скоупа фазы и трека.

**Verification:**

- `make check` и `make test` зелёные; отдельно прогнать `make test-scope P=backend/tests/security` — SIEM-тесты не должны заметить правки (они не поднимают lifespan).
- Целевой scratchpad-скрипт (в репозиторий не коммитится) поднимает приложение в двух режимах:
  - `SIEM_ENABLED=false` — в логах старта ровно одна строка `siem event emission disabled by flag`, строки `security event publisher started` нет; `app.state.security_transport_holder.get() is None`; лог с `security_event=True` проходит через процессор без исключения и ничего не публикует; `app.state.security_publisher_task` не выставлен, shutdown отрабатывает без ошибок.
  - `SIEM_ENABLED=true` — поведение байт-в-байт как до фазы: `security event publisher started`, холдер непустой, строки про выключение нет.
- Grep: `settings.siem_enabled` встречается в `backend/app/` ровно один раз (единственная точка чтения тумблера), в `runner.py`/`processor.py`/`transport.py` — ни разу.
- Смоук полного стека в docker сюда **не** входит: docker-сеть на машине сломана, проверка уходит в INTEGRATION_TEST.

---

### T4.3: Слой 2 — профиль compose для `siem-service` и `siem-db`

**Цель:** сделать так, чтобы в проде SIEM-контейнеры не поднимались **и не собирались**, а в dev поднимались как раньше — одной строкой в `.env`.

**Изменения:**

- `docker-compose.yml` — `profiles: ["siem"]` на **обоих** сервисах: `siem-service` (`:129`) и `siem-db` (`:106`). Оба, а не только `siem-service`: сервисы образуют пару (`depends_on: siem-db`), и профиль на одном из них оставил бы вторую половину поднимающейся при пустом `COMPOSE_PROFILES`. `db`, `redis`, `app` профилей не получают. Блок `volumes:` не трогается — `siem_pgdata` сохраняется (brief § 2, границы).
- `.env.example` — `COMPOSE_PROFILES=siem` рядом с `SIEM_ENABLED` в SIEM-блоке, строкой **без комментирования**. Комментарий рядом: это штатная переменная самого compose (не настройка приложения), она включает `siem-service` и `siem-db`; прод оставляет её пустой; вывести её из `SIEM_ENABLED` нельзя — compose про наши переменные ничего не знает. Закомментировать строку нельзя — на ней держится сборочная проверка siem-Dockerfile в CI (см. Cross-cutting).
- `.env.local.example` — **текст-предупреждение без присваивания**: строка вида `# COMPOSE_PROFILES=siem` здесь запрещена. Форма «закомментированное присваивание», отработанная T1 и T3, означает «раскомментируй, если нужно переопределить», а тут раскомментирование заведомо не сработает: `docker compose` читает только `.env` и **не** читает `.env.local` (проверенный факт). Поэтому в файле остаётся одна строка чистого комментария в духе «`COMPOSE_PROFILES` задаётся только в `.env` — `docker compose` не читает этот файл», без пары `VAR=value`. Это анти-грабли: остальные строки файла работают через `LOAD_ENV` в Makefile, и без пометки читатель ожидает того же и от этой.

**Verification** (сети не требует, docker-демон нужен только для парсинга):

- `docker compose config --services` при `COMPOSE_PROFILES=siem` в `.env` перечисляет `db redis app siem-db siem-service`; при пустой/отсутствующей переменной — `db redis app`.
- **Сценарий CI воспроизводится буквально**: с `.env`, скопированным из `.env.example` (как делает `ci.yml`: `cp .env.example .env`), `docker compose config --services` содержит `siem-db` и `siem-service`. Это и есть проверка, что строка `COMPOSE_PROFILES=siem` в примере осталась незакомментированной, а сборка siem-Dockerfile из CI не выпала.
- `docker compose config --profiles` показывает `siem`.
- В `.env.local.example` нет строки вида `# COMPOSE_PROFILES=...` (закомментированного присваивания) — только текст-предупреждение.
- `siem_pgdata` по-прежнему объявлен в `volumes:` в обоих случаях.
- `docker compose config` не выдаёт предупреждений про неразрешённые зависимости `depends_on`.
- Реальные `up`/`down` — вне фазы (уронили бы testcontainers-БД и упираются в сломанную docker-сеть); уходят в INTEGRATION_TEST.

---

### T4.4: Слой 3 — фронт: флаг, роут, кнопка

**Цель:** убрать из прод-бандла точки входа в SIEM-UI, ничего не удаляя из кода страницы.

**Изменения:**

- `frontend/src/shared/config/feature-flags.ts` — новый экспорт рядом с `SHOW_GROUP_B_STUBS`:

  ```ts
  export const SIEM_ENABLED =
    (import.meta.env.VITE_SIEM_ENABLED ?? "true") !== "false";
  ```

  Семантика «всё, что не литеральное `"false"`, означает включено» выбрана под дефолт `true`: сборка без build-args (`make dev-fe`, голый `npm run build`, `vite dev`) ведёт себя как сейчас. Паттерн `?? ` — по образцу `shared/api/security.ts:89`.
  Docstring (по-русски, как у соседа) фиксирует три вещи: флаг build-time и вшивается в бандл при сборке (смена требует пересборки, не рестарта); значение приезжает из бэкендового `SIEM_ENABLED` через `build.args` в compose; в отличие от `SHOW_GROUP_B_STUBS` флаг **не** привязан к `import.meta.env.DEV` — он обязан быть выставляемым именно в прод-сборке.
- `frontend/src/app/router.tsx` — `<Route path="security">` (`:34-43`) оборачивается в `{SIEM_ENABLED && ( ... )}`; `<Routes>` игнорирует falsy-детей. Импорт флага — прямым путём `@/shared/config/feature-flags` (barrel'а нет).
- `frontend/src/app/components/Sidebar.tsx` — условие кнопки становится `{SIEM_ENABLED && isAdmin && (`. RBAC-проверка остаётся: флаг её не заменяет, а сужает.
- **Не трогаются**: `SecurityRouteGuard`, страница `pages/security/`, `shared/api/security.ts` и весь код фичи — kill-switch живёт на уровне runtime/deploy, обратимость важнее вычищенного бандла (brief § 2, границы).

**Verification:**

- `make check-fe` (ESLint + Prettier) и `make test-fe` зелёные.
- **Основные (поведенческие) критерии:**
  - `make dev-fe` без переменной: роут `/security` открывается для админа, кнопка в сайдбаре на месте — dev не изменился.
  - `VITE_SIEM_ENABLED=false` в dev-режиме: кнопки нет, прямой переход на `/security` ничего не рендерит.
  - `cd frontend && VITE_SIEM_ENABLED=false npx vite build` собирается без ошибок.
- **Вспомогательный сигнал, не критерий приёмки:** grep по `dist/` на строку «Безопасность» после сборки с `VITE_SIEM_ENABLED=false`. Отсутствие строки — приятное подтверждение, наличие — **не** повод считать фазу проваленной: Rollup не обязан сворачивать кросс-модульную константу (`SIEM_ENABLED` живёт в `feature-flags.ts`, а используется в `Sidebar.tsx`/`router.tsx`), и на корректном коде мёртвая ветка вполне может доехать до бандла. Провал этого grep'а означает «посмотри, что сделал сборщик», а не «флаг не работает»; вердикт выносят поведенческие проверки выше и Vitest.
- Отдельный чанк `SecurityPage` в `dist/` при выключенном флаге критерием **не** является: попадёт он под tree-shaking или нет — деталь сборщика, требование брифа ограничено роутом и кнопкой.
- Vitest-колокацию (`Sidebar`, роутер) пишет `test-author`; фаза лишь оставляет флаг читаемым на уровне модуля, то есть тестируемым через `vi.stubEnv` + сброс модуля.

---

### T4.5: Проводка build-time флага — Dockerfile, `build.args`, `.env.example`

**Цель:** довести значение из прод-`.env` до `vite build` внутри образа, сохранив «включено» дефолтом на всех остальных путях сборки.

**Изменения:**

- `backend/Dockerfile`, стадия `frontend-build` (`:1-7`) — `ARG VITE_SIEM_ENABLED=true` и `ENV VITE_SIEM_ENABLED=$VITE_SIEM_ENABLED` **до** `RUN npm run build`. `ARG` объявляется внутри стадии (после `FROM`), иначе в неё не виден. Дефолт `true` в самом `ARG` означает, что голый `docker build` без `--build-arg` собирает включённый UI, как сейчас. Вторая стадия и оба `uv sync` не трогаются (территория T2).
- `docker-compose.yml`, `app.build` (`:43-45`) — добавляется:

  ```yaml
      args:
        VITE_SIEM_ENABLED: ${SIEM_ENABLED:-true}
  ```

  Значение выводится из `SIEM_ENABLED`, а не из одноимённой `VITE_`-переменной: у оператора остаётся один тумблер на подсистему (brief § 2), рассинхрон «бэкенд молчит, а кнопка есть» становится невыразимым.
- `.env.example` — `VITE_SIEM_ENABLED=true` в блоке `# ───────── Frontend (Vite) ─────────` (`:109`). Комментарий обязан снять двусмысленность: **в docker-сборке значение приходит из `SIEM_ENABLED` через `build.args`, эта строка описывает путь без docker** (`make dev-fe`, локальный `npm run build`); менять UI-флаг для прода нужно через `SIEM_ENABLED`, а не здесь.

**Verification:**

- `docker compose config` рендерит `app.build.args.VITE_SIEM_ENABLED` в `"true"` без переменных и в `"false"` при `SIEM_ENABLED=false` в `.env` (проверено на копии файла, сети не требует).
- Grep: `VITE_SIEM_ENABLED` присутствует ровно в четырёх местах — `feature-flags.ts`, `backend/Dockerfile`, `docker-compose.yml`, `.env.example`.
- `make check` не затронут (python-кода фаза не касается).
- Реальный `docker build` — в INTEGRATION_TEST: образ, собранный при `SIEM_ENABLED=false`, отдаёт бандл без кнопки «Безопасность»; сегодня проверку блокирует сломанная docker-сеть.

---

### T4.6: Сопутствующие дрейф-правки — `VITE_SIEM_API_URL` и пути REST

**Цель:** снять два ложных следа, которые обнаружатся при следующей реактивации SIEM.

**Изменения:**

- `.env.example:116` — `VITE_SIEM_API_URL=http://localhost:8001/siem/api` → `http://localhost:8001/api`. Обоснование в комментарии не нужно длинное, достаточно факта: dev ходит в siem-service напрямую, префикс `/siem/` появляется только за nginx. Дефолт во фронте (`security.ts:89`, `/siem/api`) верен для прода и **не** меняется.
- `doc/tech/siem-service.md:149-156` — во всех восьми строках таблицы REST путь приводится к фактическому: `/security/events` → `/api/security/events` и так далее (`APIRouter(prefix="/api/security")`).
- Правка ограничена **REST-таблицей и упоминаниями эндпоинтов siem-service**. Если в соседней прозе раздела найдётся ещё один HTTP-путь этого сервиса — привести к тому же виду; на этом всё. В частности, `/security` в фразе «lazy-loaded маршрут `/security`» ниже по разделу — это **SPA-роут React Router**, а не REST-путь: префикс `/api` ему не приписывать, строку не трогать. Их совпадающее написание — единственная причина, по которой они выглядят однородно, и именно на этом здесь легко ошибиться.

**Verification:**

- Grep по `doc/tech/siem-service.md`: REST-путей вида `` `/security/<ресурс>` `` без префикса `/api` не осталось. Упоминание SPA-маршрута `` `/security` `` (frontend-потребитель, lazy-loaded) остаётся без префикса — это ожидаемое, а не пропущенное вхождение.
- Grep по репозиторию на `8001/siem/api`: вхождений нет (кроме контекстов, где префикс ставит nginx, — там он корректен).
- Документ не содержит метапометок итераций и не противоречит коду (§ Documentation).

---

### T4.7: Runbook — секция `### SIEM` в `production.md`

**Цель:** дать точную последовательность ручных шагов на прод-VM, привязанную к окну **до merge PR в `main`**.

**Изменения:**

- `doc/tech/setup/production.md`, `## Runbook ручных шагов на прод-VM` — новый подзаголовок `### SIEM` после `### Клиентский IP`, в той же форме (нумерованные шаги, императив, привязка к моменту до merge). Переструктурировать существующее не требуется: T1 подготовил раздел ровно под это. Содержание:
  1. В боевой `.env` (`~/learnflow-ai/`, вне git) дописать `SIEM_ENABLED=false` и `COMPOSE_PROFILES=` (пустое значение). Обе строки нужны: первая гасит эмиссию, вторая — контейнеры; вывести вторую из первой compose не умеет.
  2. Остановить уже запущенные SIEM-контейнеры **явно и только их**: `docker compose --profile siem down siem-service siem-db`. Здесь важны обе части команды. `--profile siem` нужен, чтобы compose вообще увидел эти сервисы: после перевода их в профиль он перестаёт ими управлять, а `restart: unless-stopped` оставляет контейнеры работать — обычный `docker compose down` их не заметит. Список сервисов нужен, чтобы `down` не снёс всё остальное: compose берёт набор сервисов из конфига после фильтрации по профилям, поэтому без аргументов `down` останавливает и удаляет **все сервисы активного набора** — с `--profile siem` это `app`, `db`, `redis` плюс оба SIEM-сервиса, и прод лежит от этого шага до `up -d` на деплое. Именно поэтому в плане стоит команда с явными `siem-service siem-db`, а не голый `--profile siem down`: намерение брифа («остановить SIEM-контейнеры явно») сохранено, буква брифа содержит фактическую неточность — фиксируется в summary трека для pre-commit gate.
  3. UI-флаг вшивается в бандл при сборке: после merge `deploy.yml` выполняет `docker compose build`, и `VITE_SIEM_ENABLED` возьмётся из уже подготовленного `SIEM_ENABLED=false`. Если `.env` не был подготовлен до merge — потребуется отдельный `docker compose build && docker compose up -d` после правки.
  4. Проверка после деплоя: `docker compose ps` не показывает `siem-service`/`siem-db`, но показывает живые `app`, `db`, `redis` (шаг 2 их не трогал — на это и рассчитан список сервисов в команде); `docker compose exec app env | grep SIEM_ENABLED` → `false`; в логах приложения есть строка `siem event emission disabled by flag`; в UI кнопка «Безопасность» отсутствует.
  5. Обратное включение стоит двух строк в `.env` плюс `docker compose build` (UI) — данные не потеряны: volume `siem_pgdata` сохраняется, правила корреляции остаются в БД как есть.
- В том же разделе зафиксировать два **факта** (не задачи):
  - Рассинхрон `SIEM_ENABLED=true` при пустом `COMPOSE_PROFILES` безобиден: эмиссия идёт в Redis Stream без консьюмера, рост ограничен `MAXLEN ~100_000` (`transport.py:28`) — это буфер, а не утечка. Чинить нечего.
  - `location /siem/` в nginx после выключения отдаёт 502 (upstream не поднят). Рекомендация — оставить location как есть: маршрут admin-only, UI на него больше не ссылается, а удаление строки удорожило бы обратное включение и разошлось бы с референсом конфига в этом же документе. Этим закрывается вопрос, оставленный T1 (`T1/plan.md` § Open Questions #2, где операционная рекомендация делегирована T4).
- **Однострочная правка выше по документу, обязательная.** `production.md:97` (раздел с референсом nginx-конфига) сегодня констатирует 502 с оговоркой «фиксируется здесь как наблюдаемое поведение, **без рекомендации, что с этим делать**». Как только рекомендация появляется в `### SIEM`, эта оговорка делает документ противоречащим самому себе. Заменить хвост фразы на перекрёстную ссылку на новую секцию — по смыслу «рекомендация — в [§ SIEM](#siem) раздела runbook'а». Сам факт про 502 и объяснение среза префикса остаются нетронутыми; правка касается ровно этой оговорки.
- При необходимости — строка в `## Related docs` на [siem-service.md](../../../../../../tech/siem-service.md).

**Verification:**

- Раздел исполним по шагам без обращения к брифу: оператор с одним `production.md` в руках выключает SIEM на VM и проверяет результат.
- Формат согласован с `### Клиентский IP`: те же уровень заголовка, стиль нумерации и оформление команд.
- Grep по `production.md`: формулировки «без рекомендации, что с этим делать» больше нет, вместо неё — ссылка на `### SIEM`; документ не содержит двух противоположных утверждений о 502.
- Оговорка «до merge PR в `main`» присутствует и объясняет, почему окно важно (`deploy.yml` реагирует на push и сразу выполняет `git pull && docker compose build && up -d`).
- Ни одного реального секрета, домена или IP — только плейсхолдеры (правило T1.4 продолжает действовать).
- Метапометок итераций нет; раздел описывает текущее состояние (§ Documentation).

---

## Cross-cutting

После всех фаз трека:

- `make check`, `make test`, `make check-fe`, `make test-fe` зелёные.
- Три слоя выключаются независимо и проверяемы порознь: эмиссия — по INFO-строке и пустому холдеру, контейнеры — по `docker compose config --services`, UI — по поведению собранного фронта (кнопки нет, роут не рендерится). Оператору при этом видны ровно два тумблера в `.env`: `SIEM_ENABLED` и `COMPOSE_PROFILES`.
- Env-гигиена: `SIEM_ENABLED` — в `Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml` (четыре места); `VITE_SIEM_ENABLED` — в `feature-flags.ts`, `backend/Dockerfile`, `build.args` и `.env.example`; `COMPOSE_PROFILES` — раскомментированной строкой в `.env.example` плюс анти-грабля в `.env.local.example` (текст-предупреждение, без присваивания).
- **Единственное изменение dev-поведения по умолчанию** — профили compose: они опциональны по устройству самого compose, «профиль по умолчанию включён» выразить нельзя. Новый `.env`, скопированный с `.env.example`, получает `COMPOSE_PROFILES=siem` и ведёт себя как раньше; в **уже существующий** локальный `.env` (вне git, в том числе в worktree) строку нужно дописать руками, иначе `make docker-up` перестанет поднимать SIEM-контейнеры. Это осознанная цена решения, и именно поэтому строка живёт в `.env.example`. Все остальные дефолты — «включено», dev как сейчас.
- **Handoff в INTEGRATION_TEST (адресат — оркестратор/tester фазы).** Перед прогоном INTEGRATION_TEST выставить `COMPOSE_PROFILES=siem`: строкой в локальном `.env` либо env-переменной при запуске `make docker-up`. Без этого «включённый» сценарий поднимет стек без SIEM-контейнеров и проверки нельзя будет отличить от выключенного. Это же требование попадёт в `tracks/T4/test-cases.md` как предусловие сценариев — вносит `test-author`; здесь оно зафиксировано, чтобы не потеряться между фазами.
- **`COMPOSE_PROFILES=siem` в `.env.example` держит CI.** `ci.yml` (шаг «Docker build verification») делает `cp .env.example .env && docker compose build` — сборка проходит по сервисам активных профилей. Незакомментированная строка в примере — единственное, что оставляет `siem-service`/`siem-db` в этом списке; закомментируешь её — сборка siem-Dockerfile тихо выпадет из CI, и поломка образа будет обнаружена только на VM. Строка в `.env.example` обязана остаться раскомментированной, `ci.yml` при этом не правится.
- Не тронуты: Redis, volume `siem_pgdata`, код и тесты SIEM, `packages/siem-contracts` (вокабуляр сверен — без изменений), правила корреляции в БД, arch-checker/import-linter, `ci.yml`, оба `uv sync` в `backend/Dockerfile` (T2).
- Документные правки не содержат метапометок итераций и согласованы с кодом (§ Documentation).
- Готово к `test-author`: `backend/tests/siem_toggle/` (тумблер слоя 1 — единственная точка чтения `settings.siem_enabled`, проверяется через lifespan/`app.state`), Vitest-колокация во фронте (флаг — константа модуля, читается через `import.meta.env`). SIEM-файлы в `backend/tests/security/` ожидаемо не требуют правок; если правка слоя 1 их всё же задела — актуализация в скоупе `test-author` этого трека.
- T4 — последний трек перед барьером: `main.py`, `config.py`, `docker-compose.yml`, `backend/Dockerfile`, env-файлы остаются в консистентном состоянии, без «полуправок» под будущее. Проверки, требующие живого docker (полный `up` стека, реальный `docker build` образа, поведение UI в собранном образе), уходят в INTEGRATION_TEST по `tracks/*/test-cases.md` — docker-сеть на машине чинится архитектором.

---

## Open Questions

Нет открытых вопросов. Три места, где решение не выводилось из брифа напрямую, закрыты внутри плана проверенными фактами и зафиксированы здесь, чтобы не переоткрывались:

1. **`COMPOSE_PROFILES` в `.env.local.example`.** Партиция требует строку «по образцу T1/T3», но `docker compose` не читает `.env.local` (проверено эмпирически). Образец T1/T3 — это закомментированное присваивание `# VAR=value`, то есть приглашение раскомментировать; здесь раскомментирование заведомо ничего не даст. Поэтому от формы образца сознательно отступаем: в файл идёт чистый текст-предупреждение без пары `VAR=value` — он документирует ограничение и не выглядит как настройка, которую забыли включить.
2. **`location /siem/` → 502 после выключения.** T1 делегировал операционную рекомендацию разделу T4 (`T1/plan.md` § Open Questions #2). Решение — оставить location как есть, зафиксировав факт в runbook'е: маршрут admin-only, UI на него не ссылается, удаление строки удорожило бы обратное включение и разошлось бы с nginx-референсом в том же документе.
3. **Размещение `siem_enabled` в `Settings`.** Отдельная секция-комментарий, а не секция `# Security (prompt injection protection)`, куда T3 положил `llm_defense_enabled`: тумблеры гасят разные подсистемы, и соседство в одной секции читалось бы как их связь.

---

## Правки по итогам PLAN_REVIEW

Ревью нашло один блокер и пять уточнений; все приняты и внесены выше.

**Блокер — команда остановки в runbook'е (T4.7, шаг 2).** `docker compose --profile siem down` без списка сервисов останавливает и удаляет **все** контейнеры проекта, включая `app`, `db` и `redis`: прод лежал бы от этого шага до `up -d` на деплое. Шаг переписан на `docker compose --profile siem down siem-service siem-db` с объяснением обеих частей команды — зачем `--profile` (иначе compose не видит сервисы в профиле) и зачем список (иначе `down` сносит стек). Шаг 4 согласован: его проверки (`docker compose ps`, `exec app env`) предполагают живой стек — теперь это выполняется. Намерение брифа («остановить SIEM-контейнеры явно») сохранено; буква брифа содержит фактическую неточность — фиксируется в summary трека для pre-commit gate.

**Уточнения.**

1. **`COMPOSE_PROFILES=siem` держит CI (T4.3 + Cross-cutting).** `ci.yml` собирает образы после `cp .env.example .env`, поэтому раскомментированная строка в примере — единственное, что оставляет siem-Dockerfile в сборочной проверке. Запрет её комментировать вынесен в Cross-cutting, а в verification T4.3 добавлен буквальный CI-сценарий: с `.env` из `.env.example` в `docker compose config --services` есть `siem-db` и `siem-service`.
2. **Противоречие в `production.md` (T4.7).** Существующий факт про 502 несёт оговорку «без рекомендации, что с этим делать»; новая секция `### SIEM` такую рекомендацию как раз даёт. В план добавлена явная однострочная правка: оговорка заменяется перекрёстной ссылкой на `### SIEM`, плюс verification-пункт на отсутствие двух противоположных утверждений.
3. **Grep по `dist/` понижен до вспомогательного сигнала (T4.4).** Кросс-модульный константный фолдинг Rollup не гарантирован, так что мёртвая ветка может доехать до бандла и на корректном коде — критерий давал бы ложный провал. Основными оставлены поведенческие проверки (dev с флагом и без, успешная сборка) и Vitest.
4. **Область дрейф-правки сужена (T4.6).** «Привести соседнюю прозу к тому же виду» теперь ограничено REST-таблицей и эндпоинтами siem-service. SPA-роут `/security` (lazy-loaded маршрут React Router) — не REST-путь, префикс `/api` ему не приписывается; verification переформулирован, чтобы это вхождение не читалось как пропущенное.
5. **Handoff по `COMPOSE_PROFILES` оформлен явно (Cross-cutting).** Отдельной строкой: перед INTEGRATION_TEST выставить `COMPOSE_PROFILES=siem` — в локальном `.env` или env-переменной при запуске `make docker-up`. Адресат — оркестратор/tester фазы; требование продублируется в `tracks/T4/test-cases.md` силами `test-author`.
6. **Форма строки в `.env.local.example` (T4.3, Open Question #1).** Вместо закомментированного присваивания `# COMPOSE_PROFILES=siem` — текст-предупреждение без пары `VAR=value`: `docker compose` этот файл не читает, а `# VAR=value` читается как «раскомментируй меня», что здесь заведомо не сработает. Open Question #1 переформулирован под это решение.
