# Implementation Plan: chore-001 / трек T1 — клиентский IP

## Контекст

Трек чинит дефект доверия proxy-заголовкам: сейчас и middleware, и auth-роуты берут **левый** элемент `X-Forwarded-For`, который целиком подконтролен клиенту, — отсюда обход per-IP rate-лимитов и подмена `ip` в логах и SIEM-событиях. Вместо булева «доверяем прокси» вводится явный источник IP (`CLIENT_IP_SOURCE`), единая точка чтения — хелпер `backend/app/infra/client_ip.py`, и grep-абельный запрет читать proxy-заголовки где-либо ещё. Довеском трек фиксирует в документации то, на чём держится модель доверия: референсную копию nginx-конфига и инвариант «до приложения нельзя дойти мимо nginx».

Источники:

- Запись итерации: [tasklist-dogfooding.md](../../../../../tasklist-dogfooding.md) § chore-001 (B) — пункт backlog «`X-Forwarded-For` доверяется безусловно» (P2).
- Design-brief: [design-brief.md](../../design-brief.md) § 3 «Доверие proxy-заголовкам», § «Env-гигиена», § «Ручные шаги на прод-VM», § «Партиция треков» (границы T1).
- Конвенции: [conventions.md](../../../../../../tech/conventions.md) § Конфигурация через env-файлы (правило четырёх файлов), § Logging Conventions, § Dockerfile; [conventions/api.md](../../../../../../tech/conventions/api.md) — при правке роутов.
- Каталог полей security-событий: [security-events.md](../../../../../../tech/security-events.md) (строка про `ip`).

**Границы трека** (по § Партиция треков): `backend/app/infra/client_ip.py` (новый), `backend/app/api/routes/auth.py`, `backend/app/main.py` (только structlog-contextvar `ip`), `backend/app/config.py` (только две новые переменные), `.env.example`, `.env.local.example`, `docker-compose.yml`, `doc/tech/conventions.md` (правило чтения IP **плюс** строка § Dockerfile), `doc/tech/security-events.md`, `doc/tech/setup/production.md` (создание), `doc/index.md`. Тест-скоуп — новая директория `backend/tests/client_ip/`, её наполняет `test-author` отдельно.

## Согласованные факты по коду (сверено с реализацией)

- Мест чтения клиентского IP ровно два, оба воспроизводят один и тот же наивный `split(",")[0]`: `backend/app/api/routes/auth.py:76-80` (`_get_client_ip`, вызовы на `:128`, `:168`, `:207`) и `backend/app/main.py:643-649` (внутри `request_id_middleware`). Grep по `backend/` на `X-Forwarded-For` / `X-Real-IP` / `request.client` других вхождений не даёт — после врезки хелпера запрет из conventions.md сразу истинен.
- Middleware живёт в замыкании `create_app()` (`main.py:625-626`), где `settings = Settings()` уже в области видимости, — доступ к настройкам без `app.state` и без module-level state.
- Роуты получают настройки через `SettingsDep` (`api/deps.py:35-39`) — параметр уже присутствует в сигнатурах `register` / `login` / `refresh`.
- `SecurityEvent.ip` — `str | None` (`packages/siem-contracts/siem_contracts/events.py:17`), поэтому отсутствие `ip` в contextvars на health-пути контракт SIEM не ломает.
- `/health` объявлен на `main.py:687`; docker healthcheck бьёт его напрямую, минуя nginx (см. brief § 3, обоснование исключения health-пути).
- `Settings` (`backend/app/config.py`, 89 строк) — плоский `BaseSettings` с секциями-комментариями; `field_validator` уже используется (`parse_cors_origins`). `Field(ge=...)` в файле пока не встречается — импорт из `pydantic` добавляется.
- Sentinel `"unknown"` при отсутствии `request.client` уже используется в обоих местах — сохраняется.

---

## Фазы

### T1.1: Env-поверхность — `Settings` + три env-файла

**Цель:** завести `CLIENT_IP_SOURCE` и `CLIENT_IP_XFF_HOPS` одновременно во всех четырёх местах, как требует § Конфигурация через env-файлы.

**Изменения:**

- `backend/app/config.py` — секция «Client IP» рядом с auth-настройками: `client_ip_source` типа `Literal["socket", "x-real-ip", "x-forwarded-for"]` с дефолтом `"socket"`; `client_ip_xff_hops: int = Field(1, ge=1)`. Валидация значения источника делается типом (`Literal` → pydantic отвергает мусор на старте, fail-fast по § Секреты и fail-fast), отступ — ограничением `ge=1`: нулевой и отрицательный отступ дают неопределённую индексацию (brief § Env-гигиена).
- `.env.example` — обе переменные с дефолтами и комментарием, что прод ставит `x-real-ip`, а `CLIENT_IP_XFF_HOPS` значим только при `x-forwarded-for`.
- `.env.local.example` — только то, что отличается от `.env` (файл держит именно переопределения); для local dev дефолт `socket` верен, поэтому переменные попадают туда закомментированными или с явным `CLIENT_IP_SOURCE=socket` — форму выбрать по соседним блокам файла.
- `docker-compose.yml` — в `environment:` сервиса `app` (блок `:49-80`) две строки `CLIENT_IP_SOURCE: ${CLIENT_IP_SOURCE:-socket}` и `CLIENT_IP_XFF_HOPS: ${CLIENT_IP_XFF_HOPS:-1}`, по одной переменной, как требует конвенция (никакого `env_file:`).

**Verification:**

- `make check` проходит.
- `Settings()` поднимается с пустым окружением (дефолт `socket`) и падает с внятной pydantic-ошибкой на `CLIENT_IP_SOURCE=garbage` и на `CLIENT_IP_XFF_HOPS=0`.
- `docker compose config` парсится; обе переменные видны в отрендеренном окружении сервиса `app`.
- Grep подтверждает: обе переменные присутствуют в `config.py`, `.env.example`, `.env.local.example`, `docker-compose.yml` — правило четырёх мест выполнено.

---

### T1.2: Хелпер `client_ip.py` и врезка в обе точки чтения

**Цель:** свести чтение клиентского IP в одну функцию с явным источником и безопасным fallback'ом, заменив ею обе наивные реализации.

**Изменения:**

- `backend/app/infra/client_ip.py` (новый) — публичная функция `get_client_ip(request, settings) -> str`. Поведение по brief § 3:
  - `socket` (дефолт) — `request.client.host`, при отсутствии `request.client` → `"unknown"`.
  - `x-real-ip` — значение заголовка целиком (strip); заголовка нет или он пуст → падение обратно на socket **плюс** WARNING: это сигнал дрейфа nginx-конфига, а не штатный путь.
  - `x-forwarded-for` — разбор списка и взятие `CLIENT_IP_XFF_HOPS`-го элемента **справа** (hops=1 → последний элемент, дописанный ближайшим прокси); элементов меньше, чем требует отступ, или заголовка нет → socket + WARNING.
  - Health-путь исключён из fallback-предупреждения: на `/health` proxy-заголовков нет никогда (docker healthcheck идёт мимо nginx, а `location = /health` в прод-конфиге заголовков не ставит), и без исключения набегает ~8–9 тыс. WARNING в сутки, после чего сигнал ничего не значит (brief § 3, «Health-путь исключается из привязки IP»). Путь сравнивается с константой модуля; сама константа — единственное место, где он записан.
  - Логгер — `structlog.get_logger()`, keyword-стиль (§ Logging Conventions). В WARNING кладутся источник и путь, но **не** содержимое заголовка целиком.
  - Модуль не держит состояния и не читает `Settings()` сам — настройки приходят параметром (§ Module-level state).
- `backend/app/api/routes/auth.py` — `_get_client_ip` удаляется, три вызова (`:128`, `:168`, `:207`) переводятся на `get_client_ip(request, settings)`; `settings` в сигнатурах уже есть.
- `backend/app/main.py` — блок `:643-649` внутри `request_id_middleware` заменяется вызовом хелпера. На health-пути `ip` в contextvars **не биндится вовсе** (brief: «middleware не привязывает `ip` и не предупреждает на этом пути») — `request_id` и `user_agent_hash` биндятся как раньше. Комментарий `# Extract client IP (handle X-Forwarded-For for proxies)` заменяется на ссылку на хелпер.

**Verification:**

- `make check` и `make test` проходят (существующие auth-тесты не должны замечать подмены: дефолт `socket` даёт для TestClient тот же результат, что и старый код без заголовка).
- Ручная проверка трёх режимов через `curl` к `make dev`-инстансу: при `CLIENT_IP_SOURCE=socket` подделанный `X-Forwarded-For: 1.2.3.4` в лог не попадает; при `x-real-ip` берётся значение `X-Real-IP` и игнорируется `X-Forwarded-For`; при `x-forwarded-for` с `hops=1` берётся правый элемент.
- Критерий приёмки итерации: подделанный клиентом заголовок больше не даёт обхода per-IP rate-лимита `register:{ip}` / `refresh:{ip}` (сценарий, воспроизведённый в feat-002/feat-004).
- Запросы к `/health` не производят WARNING и не биндят `ip`.
- Grep `X-Forwarded-For\|X-Real-IP` по `backend/app/` даёт вхождения только в `infra/client_ip.py`.

---

### T1.3: Документные правила — conventions.md и security-events.md

**Цель:** закрепить запрет читать proxy-заголовки мимо хелпера и убрать два дрейфа, вскрытых итерацией.

**Изменения:**

- `doc/tech/conventions.md` — правило: клиентский IP берётся только через `app.infra.client_ip.get_client_ip`; `X-Real-IP` и `X-Forwarded-For` не читаются больше нигде; какой заголовок считается доверенным, решает `CLIENT_IP_SOURCE`, а не код на месте вызова. Формулировка должна быть grep-абельной — именно она снимает риск повторного наивного `xff.split(",")[0]` (brief § 3, таблица). Место: § Logging Conventions → «Security Event Logging» уже описывает, что `ip` вытягивается из contextvars автоматически, — правило встаёт туда либо соседним абзацем; альтернатива — § Секреты и fail-fast. Доменный файл `conventions/api.md` **не** трогаем: партиция закрепила за T1 именно ядро.
- `doc/tech/conventions.md:124` (§ Dockerfile) — строка «Установка через `uv sync --locked --all-packages` с cache-mount» приводится к целевому состоянию из brief § 4: `--no-dev` и `--package <имя пакета>` вместо `--all-packages`, с сохранением сути исходной формулировки (lock-файл и cache-mount обязательны, `uv pip install -e` запрещён). Правка живёт в T1 намеренно — чтобы T1 и T2 не пересекались по одному файлу (§ Партиция треков). Следствие, которое надо знать: до мержа T2 документ на одну строку опережает Dockerfile'ы; это нормально в рамках одной итерации.
- `doc/tech/security-events.md:89` — в строке поля `ip` источник `HTTP middleware (X-Forwarded-For or socket)` заменяется на формулировку через `CLIENT_IP_SOURCE`, с упоминанием, что на health-пути поле не заполняется.

**Verification:**

- Формулировка правила ищется грепом по одному очевидному запросу (`client_ip`, `X-Real-IP`) и однозначно отвечает на вопрос «можно ли прочитать заголовок здесь».
- Строка § Dockerfile согласована с brief § 4 (флаги `--no-dev`, `--package`), внутренних противоречий в разделе не осталось.
- В `doc/tech/` не осталось утверждений, что `ip` берётся из первого элемента `X-Forwarded-For` (проверяется грепом).
- Метапометок итераций в документах нет (§ Documentation: документация описывает текущее состояние).

---

### T1.4: `doc/tech/setup/production.md` — периметр, nginx-референс, runbook

**Цель:** вынести из головы и с прод-VM в репозиторий контракт периметра, от которого зависит корректность режима `x-real-ip`.

**Изменения:**

- `doc/tech/setup/production.md` (новый) — четыре смысловых блока:
  1. **Топология и инвариант доверия.** Единственный ingress — nginx на :443; порты приложения опубликованы на loopback (`127.0.0.1:${APP_PORT}:8000` в `docker-compose.yml:48`), поэтому снаружи мимо nginx до приложения не дойти. Явно сказать, что ломает модель: проброшенный наружу порт контейнера, доступ по адресу VM, соседний контейнер в compose-сети — в любом из этих случаев `X-Real-IP` становится полем, которое клиент заполняет сам, и rate limiting обходится тривиально. Edge — фильтр, а не замок (brief § 3, инвариант + SOFA-пост `ecc6a0dd`).
  2. **Санитизированный референс nginx-конфига** (`/etc/nginx/sites-enabled/learnflow`) — с плейсхолдерами вместо `server_name` и путей к сертификатам, без содержимого ключей. Обязательные элементы контракта: `proxy_set_header X-Real-IP $remote_addr` — **замена**, а не дописывание; `X-Forwarded-For $proxy_add_x_forwarded_for` остаётся для форензики, но кодом не читается; `location = /health` proxy-заголовков не ставит (расхождение фиксируется прямо в референсе комментарием); `location /siem/` срезает префикс через `proxy_pass ...:8001/`. Отдельно предупредить про `sites-available` vs `sites-enabled`: файл уже один раз разъезжался, потому что `sites-enabled/learnflow` оказался обычным файлом, а не симлинком (summary `production/chore-001-ci-cd`, находка 5). **Источник текста — см. Open Questions #1.**
  3. **Режимы `CLIENT_IP_SOURCE` в эксплуатации.** Прод — `x-real-ip`; почему дефолт `socket` (характер отказа: забыли выставить → все клиенты схлопываются в адрес docker-gateway и упираются в общий лимит, шумно и видно сразу; обратный дефолт дал бы тихую уязвимость в любом развёртывании без nginx). Известное ограничение режима `x-forwarded-for`: фиксированный отступ справа корректен только при единственной точке входа с одинаковым числом дописывающих прокси; при смешанных путях отступ попадает внутрь подконтрольной клиенту части и дыра открывается молча — поэтому переход на этот режим требует либо приведения топологии к одному ingress, либо списка доверенных адресов (brief § 3).
  4. **Runbook ручных шагов на прод-VM.** В части T1: прод-`.env` живёт вне git и новых переменных сам не получит — перед мержем PR в `main` в него дописывается `CLIENT_IP_SOURCE=x-real-ip`, и сверяется, что строка `proxy_set_header X-Real-IP $remote_addr` в nginx на месте. Привязка к моменту «до merge» существенна: `deploy.yml` срабатывает на push в `main` и сразу делает `git pull && docker compose build && up -d`, поэтому окно между мержем и подготовленной машиной означает прод с дефолтами. Раздел оформляется так, чтобы T4 дописал в него SIEM-шаги (`COMPOSE_PROFILES`, `docker compose --profile siem down`) без переструктурирования — по § Партиция треков production.md создаёт T1, дополняет T4.
- `doc/index.md` — строка нового документа в блок «Setup manuals» (сейчас там единственная запись `tech/setup/codex-cloud.md`, строки 76-77).

**Verification:**

- Документ отвечает на вопрос «что должно быть верно на VM, чтобы `CLIENT_IP_SOURCE=x-real-ip` был безопасен» без обращения к самой VM.
- Ни одного реального секрета, домена, IP или пути к ключам — только плейсхолдеры.
- Ссылка из `doc/index.md` резолвится; блок «Setup manuals» остаётся консистентным по формату с соседней строкой.
- Runbook пригоден к исполнению по шагам в момент «перед merge в `main`» — критерий из brief § «Ручные шаги на прод-VM».

---

## Cross-cutting

После всех фаз трека:

- `make check` и `make test` зелёные; `make check-fe` трека не касается (фронт в T1 не меняется).
- Единственная точка чтения IP: grep по `backend/app/` на `X-Forwarded-For`, `X-Real-IP`, `request.client` даёт вхождения только в `infra/client_ip.py`.
- Три режима `CLIENT_IP_SOURCE` ведут себя по brief § 3, включая fallback + WARNING и исключение health-пути.
- Env-переменные присутствуют во всех четырёх местах (`Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml`) — § Env-гигиена.
- Дефолтное поведение dev не изменилось: без прокси `socket` даёт тот же IP, что старый код без заголовка, — критерий «dev ведёт себя как сейчас» из brief.
- Документные правки не содержат метапометок итераций и не противоречат коду (§ Documentation).
- Готово к тому, чтобы `test-author` наполнил `backend/tests/client_ip/`: хелпер вызывается с явными `request` и `settings`, без module-level state и без чтения `os.environ` внутри.
- T1 разблокирует T3 (общие файлы `main.py`, `config.py`, env-файлы, `docker-compose.yml`) — по завершении трек должен оставить эти файлы в консистентном состоянии, без «полуправок» под будущие тумблеры.

---

## Уточнения по итогам PLAN_REVIEW (внесено оркестратором, blocker'ов ревью не нашло)

1. **Ручные кейсы трека** (нит о `test-cases.md`): ручные сценарии приёмки (три режима `CLIENT_IP_SOURCE` через `curl`, отсутствие WARNING на `/health`, прод-проверка `x-real-ip`) живут в `tracks/T1/test-cases.md` — авторит его `test-author`; автотесты — `backend/tests/client_ip/`.
2. **Контракт знания health-пути** (нит о двух местах): `client_ip.py` экспортирует публичный предикат `is_health_path(path: str) -> bool` (константа пути — приватная деталь модуля); middleware в `main.py` использует предикат для решения «не биндить `ip`». Хардкод `"/health"` в `main.py` не допускается.
3. **Форма `.env.local.example`** (нит о вариативности): закомментированная строка `# CLIENT_IP_SOURCE=socket` с комментарием-указателем, что дефолт для local dev совпадает с системным и переопределение не требуется. Явную незакомментированную строку не писать — файл держит только отличия от `.env`.

## Open Questions

Все вопросы закрыты оркестратором до PLAN_REVIEW; резолюции ниже.

1. **Источник текста для nginx-референса (T1.4, блок 2).** ЗАКРЫТ: выбран путь (б) — архитектор взял операции под контроль и одобрил снятие конфига; оркестратор снял `/etc/nginx/sites-enabled/learnflow` с прод-VM (timeweb; идентифицирована по наличию конфига и `~/learnflow-ai`) read-only. Санитизированная копия для T1.4 лежит в scratchpad оркестратора и передаётся implementer'у фазы вместе с фактами: контракт брифа подтверждён построчно (`X-Real-IP $remote_addr` — замена; `$proxy_add_x_forwarded_for` — дописывание; `location = /health` без proxy-заголовков; `/siem/` срезает префикс через `proxy_pass :8001/`); дополнительно сняты не выводимые из брифа детали — редирект :80→https, TLS-пути, SSE-блок (`proxy_buffering off`, `proxy_cache off`, `proxy_read_timeout 300s`, `proxy_http_version 1.1`, пустой `Connection`). Свежий факт для документа: `sites-available/learnflow` СНОВА расходится с `sites-enabled` (в available — устаревшая топология: фронт на :3000, `/api/`-префикс; enabled — обычный файл, не симлинк). Боевой файл — `sites-enabled`; расхождение фиксируется в production.md, приведение в порядок — ручной шаг runbook'а.
2. **Судьба `location /siem/` в референсе.** ЗАКРЫТ: референс — фактическая копия as-is (§ Documentation: документы описывают текущее состояние); допустима одна фактическая пометка, что при выключенном SIEM location отдаёт 502 (upstream не поднят). Операционная рекомендация (что с этим делать) — территория T4-раздела runbook'а.
3. **Размещение правила чтения IP в `conventions.md` (T1.3).** ЗАКРЫТ: следуем брифу и партиции — ядро `conventions.md` (бриф § 3, таблица: «Правило | doc/tech/conventions.md»). Выбор осознанный: правило кросс-доменное (auth-роуты + middleware + будущие потребители), а не специфика REST-контрактов.
