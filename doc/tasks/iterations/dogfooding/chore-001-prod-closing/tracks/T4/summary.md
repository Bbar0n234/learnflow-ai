# Summary: T4 — SIEM kill-switch

## TL;DR

Трек выключает SIEM в проде на трёх независимых слоях (эмиссия событий в python-процессе, docker-контейнеры, UI-бандл), не удаляя код подсистемы. Фаза T4.1 завела первую часть — env-поверхность операционного тумблера `SIEM_ENABLED` (bool, дефолт `true`) в четырёх местах, отработанных треками T1 и T3: `Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml`. Фаза T4.2 подключила слой 1: под `SIEM_ENABLED=false` `main.py` больше не создаёт `RedisEventTransport` и не запускает `publisher_loop`, оставляя холдер пустым; «выключено флагом» и «Redis недоступен» — различимые ветки с ровно одной INFO-строкой на старт. Фаза T4.3 подключила слой 2: `docker-compose.yml` держит `siem-service`/`siem-db` под профилем `siem`, включаемым одной строкой `COMPOSE_PROFILES=siem` в `.env`. Фаза T4.4 подключила слой 3 на стороне фронта: флаг `SIEM_ENABLED` в `feature-flags.ts` гейтит роут `/security` и кнопку «Безопасность» в сайдбаре. Фаза T4.5 довела build-time значение до `vite build` внутри docker-образа: `ARG`/`ENV` в стадии `frontend-build` (Dockerfile), `build.args` в compose, документирующая строка в `.env.example`. Фаза T4.6 закрыла два сопутствующих дрейфа: dev-пример `VITE_SIEM_API_URL` и REST-таблица `siem-service.md` приведены к фактическому префиксу `/api`. Фаза T4.7 закрыла трек операционным runbook'ом: секция `### SIEM` в `doc/tech/setup/production.md`, рядом с `### Клиентский IP`, — точная последовательность ручных шагов на прод-VM до merge PR в `main` (две строки в боевом `.env`, остановка SIEM-контейнеров сужённой командой, проверки живости остального стека, обратное включение), плюс два факта-предупреждения (безобидность рассинхрона тумблеров, `502` на `/siem/` после выключения) и снятие внутреннего противоречия документа про этот `502`. Все три слоя выключения подключены и задокументированы; трек закрыт.

## Что реализовано (T4.1)

- `backend/app/config.py` — новая секция-комментарий `# SIEM (security event emission)` между блоками Redis и Operational knobs, отдельная от `# Security (prompt injection protection)` (где T3 положил `llm_defense_enabled`): `siem_enabled: bool = True`, с комментарием из двух смысловых частей — что гасит (только эмиссию security-событий в Redis Stream из этого процесса) и чего не гасит (контейнеры — `COMPOSE_PROFILES`, UI — `VITE_SIEM_ENABLED`), плюс отметка про чтение один раз в lifespan.
- `.env.example` — `SIEM_ENABLED=true` первой строкой блока `# ───────── SIEM service ─────────` (перед `SIEM_POSTGRES_USER` и остальными настройками подсистемы), с комментарием: дефолт `true` (dev как сейчас), прод ставит `false`, переключение требует рестарта контейнера, выключает только эмиссию.
- `.env.local.example` — закомментированная строка `# SIEM_ENABLED=true` в SIEM-блоке с пометкой, что дефолт совпадает с системным и переопределение для local dev не требуется — форма, закреплённая T1 (`CLIENT_IP_SOURCE`) и T3 (`LLM_DEFENSE_ENABLED`).
- `docker-compose.yml` — `SIEM_ENABLED: ${SIEM_ENABLED:-true}` в `environment:` сервиса `app`, сразу после `REDIS_URL` (рядом с `LLM_DEFENSE_ENABLED`, разнесённым на пару строк выше через `MCP_ENCRYPTION_KEY`). В `siem-service` переменная не прокидывается — у него `env_prefix="SIEM_"`, и `SIEM_ENABLED` отобразилась бы на несуществующее поле.

## Решения и обоснования

- **Отдельная секция в `config.py`, а не соседство с `llm_defense_enabled`.** Оба тумблера — операционные kill-switch'и, но гасят разные подсистемы (inline LLM-defense vs эмиссия security-событий); совместное размещение в `# Security (prompt injection protection)` читалось бы как их связь, которой нет. Решение уже закрыто планом (Open Questions #3) — реализация ему следует буквально.
- **Место переменной в `.env.example` — первая строка SIEM-блока, без комментирования.** Тумблер управляет всей подсистемой целиком, остальные `SIEM_*` в блоке — её настройки (retention, timeouts, DB); операционная иерархия в файле отражена порядком строк.
- **`.env.local.example` не активирует переменную.** Дефолт `true` совпадает с системным, local dev в переопределении не нуждается — та же форма, что и у `CLIENT_IP_SOURCE`/`LLM_DEFENSE_ENABLED`.
- **Проверка коллизии имён с `siem_service.config.Settings`.** План фиксировал факт как уже подтверждённый эмпирически; implementer перепроверил его заново на этой фазе (см. Verification) — коллизии по-прежнему нет: `env_prefix="SIEM_"` в `siem_service.config.Settings` не создаёт поле `enabled`, конструирование не падает при `SIEM_ENABLED=false` в окружении.
- Код, читающий `settings.siem_enabled`, на этой фазе не появился — намеренно вне scope T4.1 (фаза T4.2, слой 1 — `main.py`).

## Verification (T4.1)

- `make check` — зелёный (ruff, ruff format, mypy backend/services/tools, import-linter, arch-checker; только pre-existing WARN по размеру файлов/директорий, не относящиеся к треку).
- `Settings(jwt_secret="x")` с пустым окружением → `siem_enabled is True`; с `SIEM_ENABLED=false` в окружении → `False`.
- Регрессия на коллизию префикса подтверждена заново: `siem_service.config.Settings()` конструируется без ошибок при `SIEM_ENABLED=false` и `SIEM_JWT_SECRET=<32+ chars>` в окружении; `hasattr(s, "enabled")` — `False`.
- `docker compose config` парсится без ошибок; `SIEM_ENABLED: "true"` присутствует в отрендеренном `environment` сервиса `app`; в блоке `siem-service` `SIEM_ENABLED` отсутствует (grep по срезу конфига между `siem-service:` и `siem-db:`).
- Grep подтверждает наличие переменной во всех четырёх местах: `backend/app/config.py:56`, `.env.example:72`, `.env.local.example:19` (закомментирована), `docker-compose.yml:73`.

## Что реализовано (T4.2)

- `backend/app/main.py:326-334` — блок создания `RedisEventTransport` + `publisher_loop` переписан с формы `if app.state.redis is not None:` на:

  ```python
  if not settings.siem_enabled:
      logger.info("siem event emission disabled by flag")
  elif app.state.redis is not None:
      ... как раньше ...
  ```

  «Выключено флагом» и «Redis лежит» — различимые ветки: при `SIEM_ENABLED=false` эмитится ровно одна INFO-строка `siem event emission disabled by flag` и WARNING из `create_redis` (Redis по-прежнему поднимается для `TraceStore`) не подменяется собой; при `SIEM_ENABLED=true` и недоступном Redis ветка `elif` не срабатывает — поведение байт-в-байт как до фазы (WARNING от `app/infra/redis.py`, ни INFO про флаг, ни `security event publisher started`).
- Не тронуты: создание `EventTransportHolder()` и передача его в `make_security_event_processor` (`:269-275`) — процессор остаётся в цепочке structlog и молча дропает при пустом холдере; `create_redis` (`:324`) — безусловен, Redis нужен `TraceStore`; shutdown-блок (`:630-638`) — уже защищён `hasattr("security_publisher_task")`, при несозданной задаче пропускается целиком без правок; `app.state.security_transport_holder` — выставляется всегда, вне зависимости от флага.
- Продьюсеры событий, `RedisEventTransport`, `processor.py`, вокабуляр `siem-contracts` — вне скоупа фазы, не затронуты.

## Решения и обоснования (T4.2)

- **Форма условия — `if not settings.siem_enabled: ... elif app.state.redis is not None: ...`, а не единое `if settings.siem_enabled and app.state.redis is not None:`.** Требование брифа §1 «Принятые следствия» (молчаливая деградация запрещена): единое условие с `and` схлопнуло бы оба «пустой холдер» состояния в одну неотличимую ветку без лога. `if/elif` с явной первой веткой даёт ровно одну INFO-строку на «выключено флагом» и не мешает существующему WARNING-логу `create_redis` при недоступном Redis — источники сигналов остаются раздельными и корректно атрибутируемыми.
- **`app.state.redis = await create_redis(settings)` не переносится под условие.** Redis остаётся безусловным ресурсом процесса — от него зависит `TraceStore` (`deps.py`, `routes/feedback.py`, `services/chat.py`), отключать его на основании `SIEM_ENABLED` было бы расширением скоупа флага за пределы, зафиксированные планом и брифом.

## Verification (T4.2)

- `make check` — зелёный (ruff, ruff format, mypy backend/services/tools, import-linter, arch-checker; только pre-existing WARN по размеру файлов/директорий, не относящиеся к треку).
- `make test-scope P="backend/tests/security -m unit"` — 168 passed, SIEM-тесты слоя 1 (`test_event_processor.py`, `test_event_transport.py`) правку не заметили (не поднимают lifespan).
- Grep: `settings.siem_enabled` встречается в `backend/app/` ровно один раз (`main.py:326`), в `runner.py`/`processor.py`/`transport.py` — ни разу.
- Целевой scratchpad-скрипт (не коммитится) прогнал `app.main.lifespan` до целевого блока в двух отдельных процессах (Redis реальный, недоступный — `ConnectionRefusedError`; DB и `PromptProvider` замоканы, чтобы не идти дальше блока и не требовать сети/докера):
  - `SIEM_ENABLED=false` — событие `siem event emission disabled by flag` встречается ровно 1 раз, `security event publisher started` — 0 раз; `app.state.security_transport_holder.get() is None`; `app.state.security_publisher_task` не выставлен.
  - `SIEM_ENABLED=true` + недоступный Redis — `siem event emission disabled by flag` отсутствует, `security event publisher started` отсутствует (Redis недоступен → `elif` не сработал); в логах есть WARNING `redis connection failed, proceeding without trace storage` от `app/infra/redis.py` — поведение как до фазы.
- Смоук полного стека в docker не запускался: docker-сеть на машине сломана (по вводным задачи), проверка остаётся в INTEGRATION_TEST.

## Эскалации (T4.2)

Нет. Расхождений план↔бриф по слою «Эмиссия» (design-brief.md § 2, таблица) не обнаружено — план буквально следует брифу.

## Что реализовано (T4.3)

- `docker-compose.yml` — `profiles: ["siem"]` добавлен первой строкой в обоих сервисах: `siem-db` (`:107-108`) и `siem-service` (`:130-131`). `db`, `redis`, `app` профилей не получили. Блок `volumes:` (`:175-178`) не тронут — `siem_pgdata:` остаётся объявленным как ключ верхнеуровневой секции.
- `.env.example` — `COMPOSE_PROFILES=siem` вставлен в SIEM-блок сразу после `SIEM_ENABLED=true` (перед секцией `# Database`), незакомментированной строкой, с трёхстрочным комментарием: что это штатная переменная самого compose (не `SIEM_*`-настройка приложения), что она включает `siem-service`+`siem-db`, что прод оставляет её пустой, и явным запретом её комментировать — со ссылкой на то, что на этом держится сборочная проверка siem-Dockerfile в CI.
- `.env.local.example` — в SIEM-блок после закомментированной `# SIEM_ENABLED=true` добавлена одна строка чистого текста-предупреждения (без пары `VAR=value`): `# COMPOSE_PROFILES задаётся только в .env — docker compose не читает этот файл, переопределение здесь не сработает.` Форма «закомментированное присваивание» (T1/T3) сознательно не использована — раскомментирование в `.env.local` заведомо не подействовало бы на compose.

## Решения и обоснования (T4.3)

- Реализация буквально следует плану T4.3 и Cross-cutting-правкам PLAN_REVIEW: форма строки `.env.local.example` — текст-предупреждение без присваивания (Open Question #1), запрет комментировать `COMPOSE_PROFILES=siem` в `.env.example` — ради CI-сборки siem-Dockerfile (Cross-cutting #1). Новых архитектурных решений на фазе не потребовалось.
- `profiles: ["siem"]` поставлен первым ключом сервиса в обоих блоках (единообразие, читается как метаданные сервиса раньше `image`/`build`); порядок внутри сервиса планом не был зафиксирован буквально — выбор implementer'а, не меняет семантику.

## Verification (T4.3)

- `make check` — зелёный (та же картина, что в T4.1/T4.2: только pre-existing WARN по размеру файлов/директорий).
- `docker compose config --services` без `COMPOSE_PROFILES` → `db redis app` (порядок в выводе: `db redis app`); с `COMPOSE_PROFILES=siem` → добавляются `siem-db siem-service` (полный вывод: `redis siem-db siem-service db app`, набор совпадает с ожидаемым, порядок — как формирует сам compose).
- `docker compose --profile siem config --services` даёт тот же набор, что и `COMPOSE_PROFILES=siem` в окружении.
- `docker compose config --profiles` — `siem` (список объявленных профилей, виден независимо от активации — ожидаемо).
- Сценарий CI воспроизведён буквально, но без касания реального `.env`: `.env.example` скопирован в scratchpad (`/tmp/.../scratchpad/env.ci-sim`), `docker compose --env-file <копия> config --services` → в выводе присутствуют `siem-db` и `siem-service` — строка `COMPOSE_PROFILES=siem` в `.env.example` держит CI-сборку.
- `.env.local.example` проверен на отсутствие строки вида `# COMPOSE_PROFILES=...` (закомментированного присваивания) — есть только текст-предупреждение без `=`.
- `docker compose config` (полный рендер, оба режима) не выдал предупреждений на stderr — про `depends_on` в частности.
- **Отклонение от verification-пункта плана про `siem_pgdata`.** План ожидал, что `siem_pgdata` останется видимым в `docker compose config --volumes` / полном рендере «в обоих случаях» (с профилем и без). Фактическое поведение Docker Compose v5.3.1: без `COMPOSE_PROFILES=siem` резолвер полностью выбрасывает из рендера всё, что ссылается только на исключённые профилем сервисы, — `siem-db`, `siem-service` и сам `siem_pgdata` (единственный референс — `siem-db`) не появляются нигде в выводе `docker compose config`, ни в `--services`, ни в `--volumes`, ни в полном YAML. При `COMPOSE_PROFILES=siem` volume присутствует. Источник правды — сам `docker-compose.yml`: секция `volumes:` (`:175-178`) как была, так и осталась с ключом `siem_pgdata:`, правка её не касалась; физический именованный volume на хосте это поведение `config` тоже не удаляет — команда read-only. Формальная буква verification-пункта не выполнена (профиль-фильтрация compose устраняет ключ из резолвленного вывода), но задача пункта — «правка не удалила объявление volume» — выполнена: объявление в файле-источнике нетронуто. Явно фиксирую как расхождение план↔факт для PLAN_REVIEW/архитектора, не блокирующее фазу.

## Эскалации (T4.3)

Одна, не блокирующая (см. Verification выше): verification-критерий плана «`siem_pgdata` по-прежнему объявлен в `volumes:` в обоих случаях [вывода `docker compose config`]» не подтверждается буквально под Docker Compose v5.3.1 — без активного профиля `siem` резолвер вычищает из рендера всё дерево, ссылающееся только на исключённые сервисы, включая volume. Объявление в самом `docker-compose.yml` (source of truth) не тронуто в обоих случаях. Решение не принималось самостоятельно — фиксирую факт, архитектору на решение: считать пункт закрытым по духу (source-level) или переформулировать verification под наблюдаемое поведение compose.

## Что реализовано (T4.4)

- `frontend/src/shared/config/feature-flags.ts` — новый экспорт `SIEM_ENABLED` рядом с `SHOW_GROUP_B_STUBS`: `(import.meta.env.VITE_SIEM_ENABLED ?? "true") !== "false"` — паттерн `??` по образцу `shared/api/security.ts:89`, дефолт «включено». Docstring фиксирует три вещи: build-time (вшивается при `vite build`, смена требует пересборки), значение в docker-сборке приезжает из бэкендового `SIEM_ENABLED` через `build.args`, и — в отличие от `SHOW_GROUP_B_STUBS` — флаг не привязан к `import.meta.env.DEV`, обязан быть выставляемым именно в прод-сборке.
- `frontend/src/app/router.tsx` — `<Route path="security">` обёрнут в `{SIEM_ENABLED && ( ... )}`; `<Routes>` пропускает falsy-детей. Импорт флага — прямым путём `@/shared/config/feature-flags` (barrel'а в `shared/config` нет).
- `frontend/src/app/components/Sidebar.tsx` — условие кнопки «Безопасность» стало `{SIEM_ENABLED && isAdmin && (`. RBAC-проверка (`isAdmin`) не убрана — флаг её сужает, не заменяет.
- Не тронуты: `SecurityRouteGuard`, `pages/security/`, `shared/api/security.ts` и весь код фичи — kill-switch живёт на уровне runtime/deploy, код страницы остаётся в дереве.

## Решения и обоснования (T4.4)

Реализация буквально следует плану T4.4, новых решений не потребовалось. Форма флага, место в роутере (условный ребёнок `<Routes>`) и место в `Sidebar` (композиция условий `&&`) — как зафиксировано планом и правкой N3 PLAN_REVIEW.

## Verification (T4.4)

- `make check-fe` — зелёный (tsc -b --noEmit, ESLint, Prettier --check).
- `make test-fe` (`npx vitest run`) — 29 файлов, 163 теста, все зелёные. Колокаций на `Sidebar`/`router.tsx` в репозитории пока нет — фаза оставляет `SIEM_ENABLED` читаемым на уровне модуля (тестируемо через `vi.stubEnv` + сброс модуля), написание тестов — зона `test-author` (A6).
- `cd frontend && npx vite build` (без `VITE_SIEM_ENABLED`) — собирается без ошибок, поведение по умолчанию — «включено».
- `cd frontend && VITE_SIEM_ENABLED=false npx vite build` — собирается без ошибок.
- Вспомогательный grep (не критерий, см. правку N3 PLAN_REVIEW) по `dist/assets/*.js` на строку «Безопасность»: 1 файл содержит строку при флаге включён, 0 файлов — при `VITE_SIEM_ENABLED=false`. Совпадает с ожидаемым поведением, хотя формально не гарантировано кросс-модульным constant folding'ом Rollup.
- Артефакты сборки (`dist/`, `dist-off/`) удалены после проверки, в репозиторий не попали.

## Эскалации (T4.4)

Нет.

## Что реализовано (T4.5)

- `backend/Dockerfile`, стадия `frontend-build` — `ARG VITE_SIEM_ENABLED=true` и `ENV VITE_SIEM_ENABLED=$VITE_SIEM_ENABLED` вставлены сразу после `WORKDIR /build`, до `COPY frontend/package*.json ./` и `RUN npm run build`. Дефолт `true` в самом `ARG` — голый `docker build` без `--build-arg` собирает включённый UI. Вторая стадия и оба `uv sync` (территория T2) не тронуты.
- `docker-compose.yml`, `app.build` — добавлена секция `args: VITE_SIEM_ENABLED: ${SIEM_ENABLED:-true}` сразу после `dockerfile: backend/Dockerfile`. Значение выводится из `SIEM_ENABLED`, отдельной `VITE_`-переменной для docker-пути в `.env` нет — один тумблер на подсистему у оператора.
- `.env.example` — `VITE_SIEM_ENABLED=true` добавлен в блок `# ───────── Frontend (Vite) ─────────`, сразу после `VITE_SIEM_API_URL`, с четырёхстрочным комментарием: что флаг гейтит (роут `/security`, кнопка «Безопасность»), что в docker-сборке значение приходит из `SIEM_ENABLED` через `build.args`, что эта строка описывает путь без docker (`make dev-fe`, локальный `npm run build`), и что менять UI-флаг для прода нужно через `SIEM_ENABLED`, не здесь.

## Решения и обоснования (T4.5)

Реализация буквально следует плану T4.5, новых решений не потребовалось. Место `ARG`/`ENV` в Dockerfile (сразу после `WORKDIR`, до `COPY`) выбрано implementer'ом в пределах плана — план фиксировал только «до `RUN npm run build`»; порядок с `COPY` не создаёт кэш-инвалидации по значению флага раньше необходимого, поскольку `ARG`/`ENV` не зависят от содержимого копируемых файлов.

## Verification (T4.5)

- `make check` — зелёный (та же картина: только pre-existing WARN по размеру файлов/директорий, python-кода фаза не касалась).
- `docker compose config` (env изолирован через `env -i`, реальный `.env` не читался): без `SIEM_ENABLED` в окружении → `app.build.args.VITE_SIEM_ENABLED: "true"`; с `SIEM_ENABLED=false` → `"false"`.
- Grep подтверждает `VITE_SIEM_ENABLED` ровно в четырёх местах: `frontend/src/shared/config/feature-flags.ts` (T4.4), `backend/Dockerfile` (`ARG`+`ENV`), `docker-compose.yml` (`build.args`), `.env.example`.
- `sed -n '1,9p' backend/Dockerfile` подтверждает порядок: `ARG`/`ENV` расположены до `RUN npm run build` в стадии `frontend-build`.
- Реальный `docker build` — вне фазы (сеть на машине сломана), проверка остаётся в INTEGRATION_TEST.

## Эскалации (T4.5)

Нет.

## Что реализовано (T4.6)

- `.env.example:126` — `VITE_SIEM_API_URL=http://localhost:8001/siem/api` → `http://localhost:8001/api`. Dev ходит в siem-service напрямую (без nginx), поэтому префикс `/siem/` там лишний; прод-дефолт во фронте (`security.ts:89`, `?? "/siem/api"`) — для случая за nginx, где `location /siem/` срезает префикс перед `proxy_pass` — не менялся.
- `doc/tech/siem-service.md:149-156` — восемь строк REST-таблицы приведены к фактическому префиксу: `/security/...` → `/api/security/...` (по `APIRouter(prefix="/api/security")`, `services/siem-service/siem_service/api/routes.py:26`). Строка `:160` («lazy-loaded маршрут `/security`») — SPA-роут React Router, не REST-путь — не тронута.

## Решения и обоснования (T4.6)

Реализация буквально следует плану T4.6 и границе, зафиксированной в PLAN_REVIEW (уточнение 4): правка ограничена REST-таблицей и упоминаниями эндпоинтов siem-service, соседняя проза про SPA-маршрут `/security` вне скоупа несмотря на текстуальное совпадение написания.

## Verification (T4.6)

- Grep по `doc/tech/siem-service.md` на `` `/security/ `` без префикса `/api` — вхождений нет.
- Строка `:160` с SPA-маршрутом `` `/security` `` осталась без префикса `/api` — ожидаемое, не пропущенное вхождение (проверено вручную).
- Grep по репозиторию на `8001/siem/api` — не осталось ни в коде, ни в конфигах, ни в актуальной документации (`doc/tech/`); оставшиеся вхождения — в `tracks/T4/plan.md` и `design-brief.md`, где строка описывает историческое «до фикса» состояние как часть формулировки задачи, вне скоупа фазы.
- `frontend/src/shared/api/security.ts:89` (прод-фолбэк `?? "/siem/api"`) не изменён — сверено вручную по плану.
- Оба документа не содержат метапометок итераций.

## Эскалации (T4.6)

Нет.

## Что реализовано (T4.7)

- `doc/tech/setup/production.md`, `## Runbook ручных шагов на прод-VM` — новый подзаголовок `### SIEM`, сразу после `### Клиентский IP`, той же формы (нумерованные императивные шаги, привязка к окну до merge PR в `main`): 5 шагов (правка боевого `.env` двумя строками — `SIEM_ENABLED=false` и `COMPOSE_PROFILES=` пусто; остановка SIEM-контейнеров сужённой командой с разбором обеих её частей; факт про build-time UI-флаг и когда нужен отдельный `docker compose build`; проверка после деплоя четырьмя пунктами; обратное включение) плюс два факта-предупреждения без задач на исправление (безобидность рассинхрона `SIEM_ENABLED=true`/пустой `COMPOSE_PROFILES` — `MAXLEN ~100_000`, не утечка; `502` на `/siem/` после выключения — рекомендация оставить `location` как есть).
- Однострочная правка выше по документу (`production.md:97`, референс nginx-конфига): оговорка «фиксируется здесь как наблюдаемое поведение, без рекомендации, что с этим делать» заменена перекрёстной ссылкой «рекомендация — в [§ SIEM](#siem) runbook'а ниже». Факт про 502 и объяснение среза префикса в этой строке не тронуты.
- `## Related docs` — добавлена строка на [siem-service.md](../../../../../../tech/siem-service.md) («устройство SIEM-подсистемы, которую гасит § SIEM выше»).

## Решения и обоснования (T4.7)

- **Команда остановки в шаге 2 — `docker compose --profile siem down siem-service siem-db`, а не `docker compose --profile siem down` из буквы брифа (design-brief.md § «Ручные шаги на прод-VM»).** Бриф даёт именно вторую форму. Голая форма без списка сервисов останавливает и удаляет **все сервисы активного набора**, а не только SIEM: после фильтрации по `--profile siem` активный набор — это `app`, `db`, `redis` плюс оба SIEM-сервиса, и `down` без аргументов снёс бы весь стек, включая `app`, до следующего `up -d` на деплое. Это уже разобрано и зафиксировано на уровне плана трека: PLAN_REVIEW поднял это блокером, `tracks/T4/plan.md` § «Правки по итогам PLAN_REVIEW» переписал шаг на сужённую команду с объяснением обеих её частей и явно указал сохранить фиксацию отступления в summary для pre-commit gate. Реализация T4.7 следует редакции плана после PLAN_REVIEW, а не первоначальной букве брифа: намерение брифа («остановить SIEM-контейнеры явно») сохранено полностью, буква содержала фактическую неточность (пропущенный список сервисов), не более того. Архитектурного решения на этой фазе implementer не принимал — отступление было согласовано на уровне PLAN_REVIEW ещё до старта реализации.
- **Перекрёстная ссылка вместо повтора рекомендации.** `production.md:97` (референс nginx-конфига) констатирует факт 502 без операционной рекомендации — эта роль оставлена целиком за `### SIEM`, чтобы рекомендация жила в одном месте и не разошлась при будущей правке одной из двух точек.
- Реализация буквально следует плану T4.7 в остальном: структура секции, состав шагов, формулировки двух фактов-предупреждений — без отклонений.
- **Оговорка про регистр в шаге 1 (фикс R1, часть (в)).** Runbook требовал `SIEM_ENABLED=false`, но не объяснял, что значение уходит во фронтовый build-arg `VITE_SIEM_ENABLED` сырым passthrough: pydantic принял бы и `0`/`False`, а фронт считает выключением только литеральное `false` — оператор получил бы погашенную эмиссию при живой кнопке «Безопасность» и `502` на `/siem/`. Шаг 1 дополнен абзацем-предупреждением; расширять парсинг `feature-flags.ts` под pydantic-набор не стал — это смена прод-контракта слоя 3, эскалация оставлена архитектору в R1. Комментарий `SIEM_ENABLED` в `.env.example` не тронут: он документирует только `true`/`false` и ложного обещания «любое falsy» не содержит.

## Verification (T4.7)

- Grep по `doc/tech/setup/production.md` на «без рекомендации, что с этим делать» — вхождений нет; документ не содержит двух противоположных утверждений о `502` (первое упоминание — факт с перекрёстной ссылкой, второе — тот же факт с рекомендацией в `### SIEM`).
- Grep на `profile siem down` — единственное вхождение полной команды (`docker compose --profile siem down siem-service siem-db`) в блоке кода; голого `--profile siem down` без списка сервисов как самостоятельной команды в документе нет (единственное текстовое упоминание короткой формы — внутри объясняющей прозы, как контрпример, не как исполняемая команда).
- `### SIEM` расположена сразу после `### Клиентский IP`, тот же уровень заголовка и стиль нумерации; существующие разделы не переструктурированы (сверено построчно).
- Шаги исполнимы по порядку одним документом, без обращения к брифу: правка `.env` (1) → остановка контейнеров (2) → факт про пересборку UI (3) → проверка после деплоя (4) → откат (5).
- Сервисные имена в команде шага 2 сверены с `docker-compose.yml`: `siem-service` (`:133`), `siem-db` (`:109`), оба несут `profiles: ["siem"]` (`:110`, `:134`).
- Метапометок итераций в новой секции и в правке референса нет (grep на `трек|фаза|T4\.|chore-001|итерац` — единственное совпадение в файле дособытийное, не относится к правке этой фазы: историческая ссылка на находку прошлой итерации в описании дрейфа `sites-available`/`sites-enabled`, не тронута этой фазой).
- Реальное выполнение шагов на прод-VM — вне фазы (нет доступа к VM из worktree); runbook верифицирован как документ, не как выполненная операция.

## Эскалации (T4.7)

Нет.

## Решения и обоснования (DOC_UPDATE)

- **Заведён [ADR-029](../../../../../../tech/adr/ADR-029-operational-kill-switches.md) «Операционные kill-switch'и для исследовательских подсистем».** Design-brief § «Принцип разделения конфигурации» уже формулирует решение (env-тумблер — один булев флаг на подсистему целиком, гранулярность остаётся в `configs/security.yaml`/БД правил корреляции) и его обоснование, но design-brief — артефакт итерации, который естественно перестают перечитывать после закрытия трека. Решение при этом удовлетворяет обоим критериям ADR: несёт явный trade-off (один флаг на подсистему vs per-checkpoint env-переменные vs дефолт `false`) и долгосрочно — паттерн рассчитан на переиспользование будущими kill-switch'ами, не только на два тумблера этой итерации. ADR-029 ссылается на design-brief за деталями реализации (точки врезки, слои SIEM, env-гигиена) вместо их дублирования; design-brief не переписывался. Связан из `security/architecture.md` (intro-список ADR и «Связанные документы») и `siem-service.md` (intro-список ADR и § Kill-switch).
- **Исправлен дрейф вне списка review-b: REST-таблица SIEM API в `doc/security/architecture.md` (§ «Admin Operations», строки `GET/PATCH /security/...`) осталась без префикса `/api`.** Тот же дрейф, что T4.6 уже устранил в `doc/tech/siem-service.md` (тот же коммит-скоуп T4, тот же источник расхождения — `APIRouter(prefix="/api/security")`), но `doc/security/architecture.md` не входил в файловый скоуп T4.6 и остался нетронутым. Найден при сверке review-b «Незамеченный дрейф документации» (та же секция архитектурного документа редактировалась под kill-switch), правка ограничена префиксом путей — остальной текст таблицы не тронут.
