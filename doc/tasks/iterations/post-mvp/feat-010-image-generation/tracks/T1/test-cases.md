# Test Cases: feat-010 — Генерация изображений агентом / трек T1 (Backend + Agent)

Трек T1 — новая фича: агент вызывает tool `generate_image` → OpenRouter Image API →
артефакт `type="image"` вместе с бинарём в новой таблице `artifact_blobs` (одной
транзакцией) → media endpoint отдаёт байты под JWT. Впервые в системе появляются
бинарные данные. Кейсы страхуют контракт из design-brief: атомарность «артефакт+блоб
одной транзакцией», media endpoint (200 + mime + immutable-кэш; 404 без блоба / чужой
проект / чужой пользователь / нет артефакта; JWT-auth), хелпер OpenRouter (парсинг
`b64_json`/`media_type`/`usage.cost`, маппинг ошибок на `UpstreamUnavailableError`
502/503, таймаут), fail-fast конфига (`image` обязательная), SSE-маппер эмитит
`artifact_created` для `generate_image`, и то, что байты в контекст агента не попадают
(ToolMessage текстовый).

Автотесты трека живут в `backend/tests/image_generation/` (38 тестов, зелёные). Живой
вызов OpenRouter с реальным ключом и сверка cost в Langfuse UI автоматизации не
поддаются (нет ключа в окружении) — они в ручном хвосте.

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры**: `📊` — проверка наблюдаемости (структура БД, метрики, Redis state, Langfuse); `🔴` — проверка реальных инъекций / атак / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `tests/<scope>/`); `*(регресс)*` — кейс страхует «поведение не сломалось».
- **run-log** (только у перепрогнанных кейсов): `runs: r1 ✅ → r2 ❌ (после фикса ...) → r3 ✅`.

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`/`make test`) — перепрогон всегда; ручные/UI-кейсы — перепрогон только затронутой области. Каждый перепрогон → запись в run-log.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики; не сошлось второй раз — fail + эскалация. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer**.

### Процесс (тестировщик поднимает стенд сам)

1. Инфраструктура: `make docker-up-db` (Postgres на 5432), `make migrate`, backend `make dev`, фронт `make dev-fe` — либо `make docker-up` целиком. Для ручных image-кейсов в `.env` нужен **реальный** `LLM_API_KEY` (OpenRouter) — по умолчанию плейсхолдер.
2. Акторы через UI register / `/api/auth/register`: **user-a** обычный с проектом; при необходимости **user-b** для проверки чужого проекта.
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в run-log.
4. Реальное тестирование через UI/API. После прогона — сводка (pass / failed / **deferred**).

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| Сеть / SSE | DevTools → Network |
| Артефакт+блоб | Postgres: `artifacts`, `artifact_blobs` |
| Стоимость генерации | Langfuse UI → trace agent-run → observation `generate-image` |

---

## Дизайн автотестов

Все автотесты трека — в `backend/tests/image_generation/` (изолированный скоуп; общий
фундамент — `backend/tests/conftest.py` + `packages/testing`, не дублируется). Раскладка
по модели «слой → тип теста» из `testing.md`.

**Покрываем автотестом** — по записи на суиту:

### `test_openrouter_image.py` — хелпер OpenRouter

1. **Файл**: `backend/tests/image_generation/test_openrouter_image.py` — unit, шов `httpx.MockTransport` (без сети и ключа)
2. **Тестирует**: `app/infra/image_generation.py :: generate_image`
3. **Суть**: хелпер правильно разбирает успешный ответ OpenRouter и превращает каждый
   вид сбоя в нашу типизированную ошибку: отказ провайдера — в 502, недоступность — в 503,
   битый или неполный ответ — в 502 malformed. Наружу не выходит ни один сырой сбой.
4. **Кейсы**:
   - успех: `b64_json` декодируется в байты, приходят `media_type` и `usage.cost`; `cost=None`, когда провайдер его не вернул
   - форма запроса: URL `/images`, `Authorization: Bearer`, тело `model` + `prompt` + опциональные `aspect_ratio`/`resolution` + merge `params`; незаданные опциональные аргументы не отправляются
   - non-2xx (400/429/500/502, `parametrize`) → `502 image-generation-failed`
   - таймаут и сетевая ошибка → `503 image-generation-unavailable`
   - малформед 2xx (`parametrize`, 9 кейсов: пустой/отсутствующий `data`, нет `b64_json`/`media_type`, ключи есть, но `null`/пустая строка/не-str) → `502 image-generation-malformed-response`
   - невалидный base64 → `502 malformed`

### `test_blob_storage.py` — PgBlobStorage

1. **Файл**: `backend/tests/image_generation/test_blob_storage.py` — integration, реальный Postgres с транзакционным откатом
2. **Тестирует**: `app/repositories/blob_storage.py :: PgBlobStorage`
3. **Суть**: хранилище блобов сохраняет и возвращает байты без искажений и предсказуемо
   ведёт себя на отсутствующих записях: `get` сигналит `None` (основа 404 в endpoint),
   `delete` не падает.
4. **Кейсы**:
   - `put` → `get` round-trip: точные байты (весь диапазон `0..255`) + mime
   - `get` отсутствующего → `None`
   - `delete` удаляет строку; `delete` отсутствующего — no-op

### `test_media_endpoint.py` — media endpoint

1. **Файл**: `backend/tests/image_generation/test_media_endpoint.py` — integration, аутентифицированный ASGI-клиент
2. **Тестирует**: `app/api/routes/artifacts.py :: GET /projects/{project_id}/artifacts/{artifact_id}/media`
3. **Суть**: endpoint отдаёт бинарь с корректным mime и иммутабельным кэшем, а все
   сценарии «нет данных или не твоё» схлопывает в одинаковый 404 — не раскрывая, существует
   ли артефакт.
4. **Кейсы**:
   - 200: `Content-Type` из `mime_type`, точные байты, `Cache-Control: private, max-age=31536000, immutable`
   - 404: нет блоба; нет артефакта; артефакт в чужом проекте того же юзера; проект чужого юзера
   - JWT-auth сам по себе не дублируется — закрыт суитой `tests/auth/`, клиент здесь уже залогинен

### `test_generate_image_tool.py` — tool `generate_image`

1. **Файл**: `backend/tests/image_generation/test_generate_image_tool.py` — sociable-unit, реальный Postgres под общей outer-транзакцией; шов — фейк внешнего вызова `call_generate_image` (см. conftest)
2. **Тестирует**: `app/agent/tools/image_generation.py :: make_generate_image_tool`
3. **Суть**: tool пишет артефакт и блоб атомарно — либо оба, либо ничего; передаёт
   creative-аргументы провайдеру без искажений и честно отчитывается в ToolMessage;
   при ошибке провайдера не оставляет в БД никаких следов. 📊 Отдельно гарантирует
   контракт с Langfuse: generation-observation уходит с `cost_details`, только когда
   стоимость известна.
4. **Кейсы**:
   - атомарность happy: артефакт (`type="image"`, `content=prompt`, project/thread) и блоб (`data`+`media_type`) читаются на той же транзакции — коммитнулись вместе
   - `prompt`/`aspect_ratio`/`resolution` доходят до хелпера без искажений
   - ToolMessage несёт title/id/resolution/cost; `cost=None` → метка «unknown» (не выдуманный `$0.0000`); опущенный `resolution` → «provider default»
   - атомарность negative: `UpstreamUnavailableError` из хелпера пробрасывается, ни артефакт, ни блоб не пишутся (транзакция не открывается)
   - `runtime.context is None` → `RuntimeError`
   - 📊 Langfuse: при `langfuse_enabled` открывается generation-observation (`as_type="generation"`, `model`, `cost_details={"total": cost}`); при `cost=None` `cost_details` не передаётся (мок на `langfuse.get_client` — внешний эффект, вызов и есть контракт)

### `test_stream_events_generate_image.py` — SSE-маппер

1. **Файл**: `backend/tests/image_generation/test_stream_events_generate_image.py` — unit
2. **Тестирует**: `app/agent/stream_events.py` (расширение маппера на `generate_image`)
3. **Суть**: успешная генерация рождает в SSE-потоке `artifact_created` (фронт рисует
   карточку), а ошибка tool'а — только `tool_end` (плейсхолдер снимается, карточка не
   появляется). Форма события при этом не изменилась.
4. **Кейсы**:
   - ToolMessage с `artifact` → `tool_end` + `artifact_created` (ремап `type` → `artifact_type`)
   - ToolMessage без `artifact` (ошибка tool) → только `tool_end`
   - путь `create_artifact` не дублируется — уже покрыт `tests/agent/test_stream_events.py`

### `test_image_config.py` — fail-fast конфига

1. **Файл**: `backend/tests/image_generation/test_image_config.py` — unit
2. **Тестирует**: `app/agent/config.py :: ImageConfig, AgentConfig`
3. **Суть**: без секции `image` приложение не стартует (fail-fast на загрузке конфига),
   а произвольные `params` из конфига проходят к провайдеру как есть.
4. **Кейсы**:
   - `AgentConfig` без секции `image` → `ValidationError` с `loc == ("image",)`
   - `ImageConfig.params` — дефолт `{}`; произвольные `params` сохраняются (passthrough `extra_body`)
   - реальный `configs/agent.yaml` резолвит `image.model == google/gemini-3.1-flash-image`

**Осознанно не покрываем автотестом** (что — почему — куда уехало):

- **Живой вызов OpenRouter** (реальный `b64_json`/`media_type`/`usage.cost` для
  `google/gemini-3.1-flash-image`) — нет ключа в окружении, а недетерминированный
  внешний вызов не CI-гейт (`testing.md` § Граница unit/eval); wire-формат сверен по
  офиц. доке OpenRouter и воспроизведён в `MockTransport` → ручной кейс `{T1.1}`.
- **Фактическая цифра cost в Langfuse UI** — учёт затрат живёт только в Langfuse
  (в БД не пишется) и проверяется глазами; автотест гарантирует, что наш код
  **формирует** `cost_details` из `usage.cost`, а не саму цифру провайдера
  → ручной кейс `{T1.2}`.
- **wiring в `main.py`** (`make_generate_image_tool` в `internal_tools`/`global_tools`) —
  чистая DI-склейка без бизнес-ветвлений (мягкий гейт glue по `testing.md` § DoD)
  → косвенно закрыт `tests/smoke/test_app_boot.py` (приложение поднимается) и E2E.
- **ReAct-петля целиком** (агент реально зовёт `generate_image` через граф на
  фейк-модели) — cross-cutting, ближе к E2E; для трека достаточно прямого вызова
  tool-coroutine → сквозной путь — Layer 3.
- **downgrade миграции `artifact_blobs`** — общий страж дрейфа
  (`tests/migrations/test_migration_drift.py`) уже гоняет цепочку, а миграция простая
  (autogenerate, проверена в summary T1.1) → при появлении критпуть-требования —
  вынести в migrations-скоуп.

**Замеченные прод-баги / дрейф (для fixer'а / оркестратора — сам не чиню):**

- **[test-drift, major] — закрыт.** `backend/tests/agent/test_config.py::_minimal_agent_cfg`
  конструировал `AgentConfig` **без** секции `image`, а IMPLEMENT-фаза сделала поле
  `image` обязательным (Open Question #2, fail-fast), из-за чего `make test` падал на
  3 тестах с `ValidationError: image Field required`. Фикс применён: в `_minimal_agent_cfg`
  добавлена секция `image={"model": "google/gemini-3.1-flash-image"}` (аддитивно, ассерты
  не ослаблены) — тот же механический migration, что уже был на
  `tests/personalization/conftest.py` и `test_model_config_resolver.py`. `test_config.py`
  снова зелёный (8/8), гейт восстановлен. Прод-код был корректен.

### Layer 0: Automated gate

- [x] `make check` — ruff + mypy + arch-checker (import-linter 9/9 + AST) → **0 ошибок** (по всему backend, включая новые тест-файлы). *(TEST-фаза: перепрогон — зелёный.)*
- [x] `make test-scope P=backend/tests/image_generation` — **38/38 зелёные**. *(TEST-фаза: перепрогон против запущенного Postgres — 38/38.)*
- [x] `make test` (весь backend) — зелёный: дрейф `test_config.py::_minimal_agent_cfg` пофикшен (см. закрытую ноту выше), пред-существующих падений больше нет. *(TEST-фаза: перепрогон — backend 643 passed, siem 21, contracts 64 — весь гейт зелёный.)*

---

## Ручные кейсы + статусы

Узкий ручной хвост — то, что не закрыто автотестом (нет ключа OpenRouter, проверка
глазами в Langfuse/UI).

### Layer 1: Трек T1 — Backend + Agent

- [x] `{T1.1}` 📊 **Живой вызов OpenRouter.** Прямой вызов хелпера `app.infra.image_generation.generate_image` с реальным ключом (`.env.local`), `model=google/gemini-3.1-flash-image`, короткий оригинальный промпт, `resolution` опущен (provider default). **HTTP 200**, фактическая форма ответа: top-level ключи `{created, data, usage}`; `data` — список из 1; `data[0]` содержит ровно `{b64_json, media_type}`; `media_type = "image/png"` **внутри `data[0]`**, на верхнем уровне отсутствует; `b64_json` валиден, декод → 1 467 639 байт, магия `89504e470d0a1a0a` (валидный PNG); `usage.cost = 0.0672175` (float USD, ≈ прайс 1K $0.067). Хелпер распарсил тот же payload без ошибок, байты совпали с сырым декодом. **Закрывает R2 (accepted): wire-формат подтверждён — `media_type` действительно в `data[0]`, допущение прод-кода и фейка верно.** Транзакционную атомарность «артефакт+блоб» и media endpoint страхует зелёный integration-скоуп (38/38 против реального Postgres); живой вызов через полный tool+HTTP-стенд не гонялся (порт 8000 занят другим worktree — решение архитектора), нужды нет: единственная неавтоматизируемая часть — wire-формат — сверена здесь. Стоимость прогона: один успешный вызов ~$0.067 (плюс один 400 `IMAGE_RECITATION` на первом промпте — не тарифицируется, all-or-nothing).
- [ ] 👤 `{T1.2}` 📊 **Cost в Langfuse UI.** Автопроверка невозможна в этом окружении: `LANGFUSE_PUBLIC_KEY`/`SECRET_KEY` в `.env.local` — плейсхолдеры (19 символов, не формат `pk-lf-`/`sk-lf-`), `LANGFUSE_BASE_URL` не задан → `auth_check()` против `cloud.langfuse.com` возвращает **401 Invalid credentials**, т.е. в приложении `langfuse_enabled=False`, живого трейса создать нельзя. Формирование payload'а уже закрыто автотестом `test_generate_image_emits_langfuse_observation_with_cost` (as_type=generation, model, `cost_details={"total": cost}`) и `*_omits_cost_when_unknown` (при `cost=None` `cost_details` отсутствует); реальная цифра `usage.cost=0.0672175` подтверждена в `{T1.1}`. **Инструкция архитектору:** прогнать с валидными Langfuse-ключами (реальный проект) — либо `make dev` + чат-запрос обложки, либо тот же прямой прогон tool'а с `langfuse_enabled=True`; в Langfuse UI открыть trace → observation `generate-image`, убедиться: тип generation, `model=google/gemini-3.1-flash-image`, `cost_details.total` ≈ фактический `usage.cost` (1K ≈ $0.067, 2K ≈ $0.101).
- [x] `{T1.3}` **Ошибка провайдера не тарифицируется и не пишет данные.** Живой прогон хелпера с двумя провокациями (обе не тарифицируются): (1) битый ключ → реальный upstream 401 → `UpstreamUnavailableError status=502 code='image-generation-failed'`; (2) битый base URL → connection error → `UpstreamUnavailableError status=503 code='image-generation-unavailable'`. Хелпер поднимает исключение **до** открытия `session.begin()` в tool'е (транзакция физически не начинается), поэтому новых строк в `artifacts`/`artifact_blobs` быть не может, а Langfuse generation-observation создаётся только после успешной транзакции — при ошибке не создаётся. Инвариант «writes nothing» и обёртка `ToolMessage(status="error")` через `ToolNode.handle_tool_errors` закрыты автотестами (`test_generate_image_provider_error_writes_nothing`, error-mapper); живой слой подтвердил маппинг реальных 4xx/сетевой ошибки на 502/503.

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [x] **Агент → артефакт+блоб → media endpoint end-to-end.** (INTEGRATION_TEST, живой стенд backend :8010 + real OpenRouter key.) Реальный чат-стрим (POST `.../messages`, JWT): агент попросили сгенерировать простую тестовую картинку 512px → по SSE пришли ровно `tool_start(tool=generate_image, call_id=call_3fa34e3a…)` → `tool_end(тот же call_id)` → `artifact_created(id=b868312d…, artifact_type=image, title="Test Image: Red Circle on White")` — порядок и совпадение `call_id` (ключ фронт-плейсхолдера) как в design-brief sequence. `GET /api/projects/{pid}/artifacts/{aid}/media` под JWT → **200**, `Content-Type: image/jpeg`, `Cache-Control: private, max-age=31536000, immutable`, тело — валидный JPEG (магия `ffd8ffe0`), `Content-Length=33720`. БД (`artifacts`⋈`artifact_blobs`): `type=image`, `content`=промпт агента («A single solid red circle…»), `mime_type=image/jpeg`, `length(data)=33720` — байты media == блоб в БД, артефакт+блоб коммитнулись вместе. Нюанс: модель вернула **JPEG** (не PNG как в `{T1.1}`) → подтверждает, что `mime_type` берётся динамически из `data[0].media_type`, а не захардкожен. Стоимость: одна успешная генерация 512px = **$0.0457** (из ToolMessage-текста; совпадает с прайс-таблицей design-brief 512px≈$0.045).

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] 👤 **Полный journey: генерация → карточка-превью → вьюер.** Backend-часть journey закрыта Layer 2 выше (генерация → артефакт+блоб → media отдаёт реальный бинарь); визуальные шаги (плейсхолдер-шиммер во время генерации, карточка-превью 64×40, вьюер с картинкой/caption/скачиванием) требуют браузера — вынесено архитектору. Вьюер/карточка/плейсхолдер-рендер покрыты фронт-автотестами (`ImageViewer.test.tsx`, `ArtifactCard.test.tsx`, `MessageList.test.tsx`, `useAgentStream.test.ts`). **Готовый живой артефакт для проверки глазами:** на стенде (backend feat-010 + БД `learnflow`:5432) войти `tester-1784153640` / `test-pass-1234`, проект `img-test` (`d1ddb38c-2ccc-4d68-9a17-24b0f3c33618`), image-артефакт `b868312d-8de7-4df4-a21e-99eeff349925` (реальный JPEG, красный круг) — открыть карточку и вьюер, свериться с мокапом. (Кросс-трек T1+T2; браузер.)

---

## Находки ревью [severity+owner]

Ревью T1 против § Чек-лист ревьюера. Прочитаны все 6 тест-файлов + conftest, 3 аддитивные
миграции существующих тестов, весь прод-код скоупа (`infra/image_generation.py`,
`repositories/blob_storage.py`, `agent/tools/image_generation.py`, `agent/stream_events.py`,
`api/routes/artifacts.py`, `agent/config.py`) и design-brief § Вызов модели. Фейки сверены
с прод-контрактом: `httpx.MockTransport`-хэндлеры эмитят ровно ту форму
(`data[0].b64_json` + `data[0].media_type` + `usage.cost`), которую парсит прод и которую
фиксирует design-brief; фейк `call_generate_image` совпадает с сигнатурой инфра-функции;
Langfuse-стаб (`start_as_current_observation`) — совпадает с прод-вызовом. Маппинг ошибок
502/503, ветки 404 media, fail-fast конфига, SSE-remap — покрыты и соответствуют коду.

- **R1 minor [test] — закрыт.** Добавлен `test_generate_image_blob_write_failure_rolls_back_artifact`:
  `PgBlobStorage.put` замокан на бросок исключения строго внутри `session.begin()` (после того как
  `ArtifactRepository.create` уже сфлашил артефакт), ассерт — читатель на той же outer-транзакции
  не видит ни артефакта, ни блоба. Инвариант «сбой записи блоба в середине транзакции → артефакт
  откатился» теперь зафиксирован тестом, а не только семантикой `session.begin()`. Скоуп зелёный (38/38).

- R1 minor [test] test_generate_image_tool.py:201-231 — единственный negative на атомарность
  (`*_provider_error_writes_nothing`) проверяет отказ **до** открытия транзакции (хелпер
  бросает раньше `session.begin()`). Настоящий атомарный инвариант — «артефакт создан, затем
  блоб-запись падает внутри той же `session.begin()` → артефакт откатывается» — не проверяется
  ни одним тестом, хотя design-brief делает атомарность бинарей ключевой новизной итерации, а
  имя теста `*_atomically` заявляет её. Happy-путь доказывает «оба записались», provider-error —
  «оба отсутствуют при отказе до txn»; ветка «блоб упал в середине → артефакт не осел» опирается
  только на семантику `session.begin()` (гарантия SQLAlchemy), но не зафиксирована тестом.
  → добавить кейс с инъекцией сбоя в `PgBlobStorage.put`/констрейнт после `ArtifactRepository.create`,
  ассертить, что артефакт в БД отсутствует (all-or-nothing внутри транзакции).

- **R2 minor [test] — accepted (не фиксится автотестом).** Enshrined-риск: фейк воспроизводит то же
  допущение о `media_type` внутри `data[0]`, что кодирует прод, — дивергенцию с реальным wire-форматом
  OpenRouter автотест по построению поймать не может. Крит-верификация вынесена на ручной `{T1.1}`
  (живой вызов). Ослаблять/расширять фейк без живой сверки нельзя. Оставляю как известное ограничение
  автоматического слоя.

- R2 minor [test] test_openrouter_image.py:56-63,133-134 (+ прод infra:103-105) — и фейк, и прод
  разделяют допущение, что `media_type` лежит внутри `data[0]` (а не, например, в теле верхнего
  уровня или в заголовке). Если реальный wire-формат OpenRouter расходится с этим допущением,
  весь unit-набор останется зелёным (фейк воспроизводит то же допущение, что кодирует прод) —
  классический enshrined-риск «фейк согласован с реализацией, но не с внешним контрактом».
  Автотест поймать это не может по построению; ловит только ручной `{T1.1}` (живой вызов).
  Допущение соответствует design-brief § Вызов модели (источник контракта по заданию), поэтому
  не blocker — фиксирую как известное ограничение автоматического слоя, крит-верификация висит
  на ручном `{T1.1}` (уже помечен). Ослаблять/расширять фейк без живой сверки нельзя.

- **R3 minor [doc] — закрыт.** Дрейф-нота «Замеченные прод-баги / дрейф» и Layer-0 статус
  актуализированы по факту: фикс `test_config.py::_minimal_agent_cfg` уже в дереве (подтверждено
  `test_config.py` 8/8 зелёный), строка «⚠️ make test — 3 упавших» заменена на зелёный статус,
  нота помечена закрытой.

- R3 minor [doc] test-cases.md:127-139,145 — секция «Замеченные прод-баги / дрейф» и Layer-0
  статус утверждают, что `test_config.py::_minimal_agent_cfg` **не** пофикшен и `make test` даёт
  3 упавших. В рабочем дереве фикс уже применён: `git diff backend/tests/agent/test_config.py`
  показывает добавленную секцию `image` в `_minimal_agent_cfg` (аддитивно, ассерты не ослаблены).
  Дрейф-нота и строка «⚠️ make test — 3 упавших» устарели. → обновить статус на закрытый
  (фикс в дереве) либо снять ноту.

Проверено и чисто: (1) false-green нет — все ассерты содержательны, проверяют результат/побочный
эффект, а не поведение моков; (2) флак — изоляция через транзакционный откат (общий `db_session`
для blob/media; кастомный `outer_conn`+savepoint для tool, обоснован в conftest docstring, доступ
последователен, не конкурентен), loop scope наследуется от корневого харнеса; (3) дубли по правилу —
Postgres только под integration (blob/media/tool), хелпер и SSE/config на фейках; mock только на
внешних эффектах (httpx-транспорт, Langfuse-клиент), внутренние коллабораторы (`ArtifactRepository`,
`PgBlobStorage`) настоящие; (4) нейминг `test_<unit>_<condition>_<expected>`, `parametrize` на
таблицах ошибок, скоуп-директория корректна, `packages/testing`-фабрики переиспользованы;
(5) критпути 404 media (без блоба / нет артефакта / чужой проект того же юзера / проект чужого
юзера), маппинг 502/503 + timeout + network + malformed + invalid-base64, обе ветки SSE-remap,
fail-fast конфига — покрыты; (6) граница unit/eval соблюдена — живой cost/качество вынесены в
ручной хвост, в гейте только формирование `cost_details`; (7) A6/целостность — миграции трёх
существующих тест-файлов строго аддитивны (только добавлен `image=ImageConfig(...)`/секция),
ни один ассерт не ослаблен, чужие тесты под реализацию не переписаны. [prod]-эскалаций нет.

---

## Покрытие (опционально)

| Контракт из design-brief | Закрывающие автотесты |
|---|---|
| Атомарность «артефакт+блоб одной транзакцией», ошибка → ничего | `test_generate_image_tool.py::*_atomically`, `*_provider_error_writes_nothing` |
| media: 200 + mime + immutable | `test_media_endpoint.py::*_bytes_mime_and_immutable_cache` |
| media: 404 без блоба / чужой проект / чужой юзер / нет артефакта | `test_media_endpoint.py::*_without_blob/_missing_artifact/_another_project/_other_users_project` |
| Хелпер: парсинг b64/mime/cost | `test_openrouter_image.py::*_decodes_bytes_media_type_and_cost`, `*_missing_cost_yields_none` |
| Хелпер: маппинг ошибок 502/503 + таймаут | `test_openrouter_image.py::*_non_2xx/_timeout/_network_error/_malformed/_invalid_base64` |
| fail-fast: `image` обязательна | `test_image_config.py::*_without_image_section_raises` |
| SSE: `artifact_created` для `generate_image` | `test_stream_events_generate_image.py::*` |
| ToolMessage текстовый (байты не в контекст) | `test_generate_image_tool.py` (возврат `tuple[str, dict]`, байты только в БД) |
| 📊 Langfuse cost_details из usage.cost | `test_generate_image_tool.py::*_langfuse_observation_with_cost/_omits_cost_when_unknown` |
| PgBlobStorage put/get/delete | `test_blob_storage.py::*` |
