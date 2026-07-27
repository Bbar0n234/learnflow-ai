# Implementation Plan: feat-002-chat-ux / трек T1 — Backend: контракты чатов + auto-title

## Контекст

Трек закрывает бэкендовую половину итерации: чат перестаёт получать имя от пользователя (его ставит сервер плейсхолдером и переписывает дешёвая LLM), у чатов появляются rename и delete с полным каскадом, а готовый title доезжает до фронта новым не-терминальным SSE-событием.

Источники:

- Запись итерации — [tasklist-dogfooding.md](../../../../../tasklist-dogfooding.md) § feat-002 (C): Chat UX
- Design-brief — [design-brief.md](../../design-brief.md); границы трека — § Партиция треков (T1), § Scope boundaries, § Контракты
- Конвенции — [conventions.md](../../../../../../tech/conventions.md) (env-workflow, логирование, коммиты, тестирование), [conventions/api.md](../../../../../../tech/conventions/api.md) (status codes, ownership, нейминг chat/thread), [conventions/db.md](../../../../../../tech/conventions/db.md) (commit-правила), [conventions/agent.md](../../../../../../tech/conventions/agent.md) (Reasoning LLMs, Prompt Naming), [conventions/testing.md](../../../../../../tech/conventions/testing.md)
- Архитектурная дока — [streaming.md](../../../../../../tech/streaming.md) (протокол SSE), [backend.md](../../../../../../tech/backend.md) (слои, правила вызовов), [prompt-management.md](../../../../../../tech/prompt-management.md) (seed/sync промптов)

Отдельной секции «критерии приёмки» в брифе нет — verification опирается на строки таблицы § Контракты и на поимённые решения § Auto-title модуль / § Rename и delete.

**Верификация API по установленным пакетам (выполнена на этапе планирования):**

- `AsyncPostgresSaver.adelete_thread(thread_id: str) -> None` существует в установленной версии (`.venv/.../langgraph/checkpoint/postgres`), сигнатура принимает **строку**, не UUID.
- `PromptProvider.get_prompt(name, **variables)` тянет `{name}--{label}` из Langfuse с файловым fallback `configs/prompts/{name}.txt`; `_seed_prompts` в `main.py` итерируется **по ключам `configs/prompts.yaml`**, поэтому запись `title` в реестре + файл `configs/prompts/title.txt` дают seed/sync автоматически, без правок кода сидера. Тот же реестр читает `backend/scripts/sync_prompts.py`.
- `_build_chat_model` (`backend/app/infra/llm.py`) — единый приватный билдер, всегда `ReasoningChatOpenAI`; keyword-параметры `max_tokens / temperature / timeout / max_retries`; `timeout` маппится в `request_timeout`. Публичные фабрики (`create_summarization_llm`, `create_guard_llm`) — образец для `create_title_llm`.

**Границы, которые трек не переходит:** `doc/**` (актуализация — фаза DOC_UPDATE после барьера), `frontend/**`, `backend/tests/conftest.py`, `packages/testing/**`, `Makefile`. Потребность их править — эскалация оркестратору.

**Per-track гейт** (из § Партиция треков): `make check` + `make test-scope P=backend/tests`. Полный `make ci` внутри трека не гоняется. Новые автотесты пишет позже `test-author`; задача implementer'а на каждой фазе — не оставлять красными существующие тесты (включая легализованные точечные правки чужих тест-файлов в T1.3).

## Фазы

### T1.1: Контракты создания и переименования чата

**Цель:** сервер сам ставит плейсхолдер названия при создании чата, а переименование появляется отдельным endpoint'ом с лимитом длины.

**Изменения:**

- Новый нейтральный модуль констант в сервисном слое (например `backend/app/services/constants.py`) — `DEFAULT_CHAT_TITLE = "Новый чат"` и лимит длины названия `100` (резолюция PLAN_REVIEW: отдельный модуль вместо `services/chat.py`, чтобы `api/schemas` импортировали константу, а не весь модуль чат-сервиса с его зависимостями; направление `api → services` разрешено import-linter, обратное — нет, поэтому носитель в сервисном слое).
- `backend/app/services/chat.py` — `create_chat` больше не принимает `title` снаружи — ставит константу; `commit`-до-return сохраняется как есть. Новый метод `rename_chat` поверх уже существующего `ThreadViewRepository.update(title=...)`.
- `backend/app/api/schemas/chats.py` — `ChatCreate` удаляется целиком (вместе с реэкспортом в `backend/app/api/schemas/__init__.py` — импорт и `__all__`); добавляется `ChatUpdate { title: str }` с `Field(min_length=1, max_length=<лимит>)`.
- `backend/app/api/routes/chats.py` — `create_chat` теряет параметр тела (запрос без body); новый `PUT /projects/{project_id}/chats/{chat_id}` → `200 ChatResponse`, ownership через штатную dependency `UserThread` (ручных проверок в handler'е не пишем — api.md § Ownership).
- `backend/app/api/schemas/projects.py` — попутный дрейф-фикс: `ProjectUpdate.name` получает тот же лимит длины (сейчас без ограничения вопреки db.md/api.md).
- `backend/tests/chat/test_chat_routes.py` — существующие вызовы `POST /chats` с телом `{"title": ...}` приводятся к запросу без тела; ожидание дефолтного title меняется с `"New Chat"` на `"Новый чат"`. `backend/tests/chat/test_chat_service.py` — вызовы `service.create_chat(..., title=...)` приводятся к новой сигнатуре (оба файла — тест-скоуп трека).

**Verification:**

- `make check` проходит.
- `make test-scope P=backend/tests/chat` и `P=backend/tests/projects` — зелёные.
- Контракт § Контракты: `POST /projects/{id}/chats` принимается **без тела** и возвращает `201` с `title == "Новый чат"`; передача постороннего тела не влияет на результат. `PUT /projects/{id}/chats/{chat_id}` возвращает `200 ChatResponse` с новым названием; чужой чат — `404`; превышение лимита длины — `422`.
- Rename разрешён и на чате с `security_blocked = true` (`require_unblocked_thread` остаётся только на `POST /messages`).

### T1.2: Удаление чата с полным каскадом

**Цель:** `DELETE` чата убирает не только строку `thread_views`, но и полиморфные disables и checkpoints LangGraph — в безопасном порядке.

**Изменения:**

- `backend/app/repositories/mcp_server.py` — новый `cleanup_disables_for_thread(thread_id)` по образцу `cleanup_disables_for_project`: disables со scope `('thread', thread_id)` **плюс** disables, ссылающиеся на `ThreadMCPServer` этого чата. Вызывается до удаления треда, пока каскад не стёр серверы.
- `backend/app/services/agent_runner.py` — в Protocol `AgentRunner` добавляется `async def delete_thread(*, thread_id: uuid.UUID) -> None`.
- `backend/app/agent/runner.py` — `LangGraphAgentRunner` получает checkpointer **keyword-only параметром с дефолтом `None`** (жёсткое ограничение § Партиция треков п. «а» — позиционные конструкторы в чужих тестах не трогаем) и реализует `delete_thread`: `adelete_thread(str(thread_id))`, при `None` — no-op с `logger.warning`.
- `backend/app/main.py` — checkpointer прокидывается в конструктор runner'а (он уже в скоупе lifespan, `app.state.checkpointer`).
- `backend/app/services/chat.py` — `delete_chat`: сначала транзакция БД (cleanup disables → `repo.delete` → commit), затем best-effort `agent_runner.delete_thread` под барьером `try/except` + `logger.warning(..., exc_info=True)`. Порядок нарушать нельзя — обоснование в брифе § Rename и delete.
- `backend/app/api/routes/chats.py` — `DELETE /projects/{project_id}/chats/{chat_id}` → `204`, **идемпотентный**: ownership резолвится вручную в handler'е по образцу `delete_project` (dependency `UserThread` дала бы 404 на уже удалённом чате и сломала идемпотентность); отклонение от правила «ownership только через dependencies» — сознательное и задокументированное в брифе.
- `backend/tests/chat/conftest.py` — фейковый runner дополняется методом `delete_thread` (иначе `ChatService.delete_chat` не прогонится на существующих фикстурах).

**Verification:**

- `make check` проходит (в т.ч. `lint-imports` — новый метод не нарушает слои).
- `make test-scope P=backend/tests/chat` и `P=backend/tests/agent` — зелёные (проверка, что конструкторы runner'а в чужих тестах не сломаны).
- Контракт § Контракты: `DELETE` существующего чата → `204`; повторный `DELETE` того же id → тоже `204`; чужой чат → `404`; чат с `security_blocked = true` удаляется штатно.
- Каскад по таблице § Rename и delete: после удаления нет строк `mcp_server_disables` для этого треда; артефакты остаются с `thread_id = NULL`; падение `adelete_thread` не роняет запрос и не откатывает удаление.

### T1.3: Конфиг, фабрика LLM и промпт для auto-title

**Цель:** появляется вся обвязка для служебного title-вызова — обязательная секция конфига, фабрика модели, таймаут в env и промпт в реестре Langfuse.

**Изменения:**

- `backend/app/agent/config.py` — `TitleConfig(BaseModel)` (`model: str`, `extra_body: dict = {}`) и **обязательное** поле `title: TitleConfig` в `AgentConfig` (fail-fast на старте, ровно как `image`).
- `configs/agent.yaml` — секция `title` с моделью `deepseek/deepseek-v4-flash` и `extra_body.reasoning` в единой проектной форме (conventions/agent.md § Reasoning LLMs) с **минимальным effort (`low`)** — резолюция PLAN_REVIEW: служебный однострочный вызов под коротким таймаутом; `medium` (как у `summarization`) повышал бы риск систематических таймаутов и постоянной деградации до плейсхолдера. В `available_models` модель **не** добавляется — секция служебная.
- `backend/app/infra/llm.py` — `create_title_llm(settings, config: TitleConfig)` через `_build_chat_model` с `timeout=settings.llm_title_timeout_seconds` и `max_retries=settings.llm_max_retries`.
- `backend/app/config.py` + `.env.example` + `docker-compose.yml` — новая переменная `LLM_TITLE_TIMEOUT_SECONDS` (порядка 20 с) одним atomic change по образцу `LLM_IMAGE_TIMEOUT_SECONDS`. `.env.local.example` — см. Open Questions (файл держит только локальные переопределения, ни один `LLM_*_TIMEOUT` в нём не заведён).
- `configs/prompts/title.txt` — системный промпт: короткое название на языке сообщения, без кавычек и завершающей пунктуации, одна строка; текст пользователя подаётся отдельным сообщением и оформляется как **данные** (wrapper `user_message` из `configs/prompt_fragments.yaml`), не как инструкция.
- `configs/prompts.yaml` — запись `title` с `source: agent.title` и ключами `model` / `extra_body` (по образцу `summarization`), чтобы `_seed_prompts` и `make sync-prompts` подхватили промпт без правок кода.
- Легализованные точечные правки чужих тестов (только добавление `title=` / ключа `"title"`, ничего сверх): `backend/tests/agent/test_config.py`, `backend/tests/personalization/conftest.py`, `backend/tests/personalization/test_model_config_resolver.py`, `backend/tests/subagents/test_runner.py` (там же локальный хелпер по образцу `_min_image`), а в `backend/tests/agent/test_pricing_consistency.py` — добавление `agent.title.model` в `_active_model_slugs`.

**Verification:**

- `make check` проходит.
- `make test-scope P=backend/tests` зелёный целиком — в первую очередь `tests/agent`, `tests/personalization`, `tests/subagents` (проверка, что обязательность секции нигде не оставила красноты).
- Конфиг-контракт: удаление секции `title` из `agent.yaml` роняет загрузку конфига на старте (fail-fast, как у `image`).
- `test_active_models_each_match_exactly_one_pricing_entry` остаётся зелёным — слуг `deepseek/deepseek-v4-flash` уже покрыт `configs/pricing.yaml`.

### T1.4: Генератор title как fire-and-forget сервис

**Цель:** появляется компонент, который по запросу генерирует название чата в собственной сессии БД, держит реестр задач и никогда не роняет чужой поток.

**Изменения:**

- Новый модуль сервисного слоя (например `backend/app/services/chat_title.py`) — класс-генератор, собираемый в lifespan и живущий в `app.state`. Состав по решениям брифа § Auto-title модуль:
  - конструктор принимает `session_factory`, `settings`, `TitleConfig`, `PromptProvider`, `PromptFragmentsConfig`, флаг `langfuse_enabled`; внутри держит реестр `dict[uuid.UUID, asyncio.Task]`. Реестр живёт **в объекте**, а объект — в `app.state`: требования брифа (ссылка вне генератора `send_message`, discard в done-callback, in-flight-guard по `thread_id`, отсутствие module-level state) выполняются, а `ChatService` не ходит в `app.state` руками;
  - публичный метод «запустить генерацию для чата, если её ещё нет» — сигнатура `(thread_id, content)`, где `content` — текст первого сообщения пользователя (вход генерации по брифу § Auto-title); возвращает handle задачи (или `None`, когда задача уже в полёте) — это то, что relay-цикл кладёт себе в локальную переменную;
  - тело задачи: открыть **собственную** сессию из `session_factory` (образец — `app/agent/tools/image_generation.py`), перечитать `ThreadView`; если чат исчез, помечен `security_blocked` или его `title` уже не равен `DEFAULT_CHAT_TITLE` — выйти, ничего не записав; иначе вызвать LLM, пост-обработать ответ (strip, срез переносов, усечение до общей константы лимита из T1.1), записать через `ThreadViewRepository.update`, вернуть готовый title наружу;
  - барьер: любое исключение → `logger.warning("chat title generation failed", thread_id=..., exc_info=True)` и `None` как результат; успех → `logger.info("chat title generated", ...)`;
  - трейс: `get_client().start_as_current_observation(as_type="generation", ...)` под `contextlib.suppress(Exception)`, по образцу `generate_image` — сознательная замена образца относительно брифа («по образцу summarization»), резолюция PLAN_REVIEW: summarization трассируется callback-хендлером внутри графа, что вне request/graph-контекста fire-and-forget задачи не воспроизводится; `generate_image` — ближайший образец задачи вне графа.
- `backend/app/main.py` — сборка генератора в lifespan (после `PromptProvider` и `session_factory`), `app.state.<title_generator>`.
- `backend/app/api/deps.py` — `get_chat_service` прокидывает генератор в `ChatService` (опциональная зависимость с дефолтом `None`, чтобы ASGI-тесты без lifespan не ломались).
- `backend/app/services/chat.py` — конструктор принимает генератор; поведение `send_message` в этой фазе ещё не меняется.

**Verification:**

- `make check` проходит.
- `make test-scope P=backend/tests` зелёный (в частности `tests/chat` — конструктор `ChatService` сменился, фикстуры трека должны это пережить).
- Приложение поднимается: `make docker-up` (или `make dev`) — в логах нет ошибок инициализации, генератор в `app.state` есть.
- Решения брифа, проверяемые на этой фазе: повторный запрос генерации при уже идущей задаче новой задачи не создаёт; задача, дошедшая до записи, ничего не пишет, если чат удалён / `security_blocked` / title уже не плейсхолдер; отказ LLM оставляет название «Новый чат» и логируется `warning`.

### T1.5: Запуск генерации из relay-цикла и событие `title_updated`

**Цель:** title рождается ровно тогда, когда guard пропустил ввод, и доезжает до клиента новым не-терминальным SSE-событием в том же стриме.

**Изменения:**

- `backend/app/services/chat.py::send_message`:
  - триггер — «title ещё плейсхолдер»: `thread_view.title == DEFAULT_CHAT_TITLE` (истории из checkpointer не читаем);
  - запуск — **после guard**: на первом событии агента, отличном от `security_block` (события `trace_id` в цикле уже отфильтрованы `continue`, проверку ставить после этого фильтра), с передачей текста первого сообщения (`content`) в метод генератора. При первом событии `security_block` задача не создаётся вовсе;
  - эмит — между событиями агента: если handle задачи готов (`task.done()`) и вернул непустой title, в поток уходит `StreamEvent(type="title_updated", data={"title": ...})`, после чего handle сбрасывается (событие ровно одно за ран);
  - специальной механики ожидания (`asyncio.wait` по двум источникам) не строим — принятое ограничение брифа: на «молчащем» ране title ждёт следующего события агента.
- `backend/app/api/routes/messages.py` — **не меняется**: `_event_generator` сериализует событие generic-механикой.

**Verification:**

- `make check` проходит.
- `make test-scope P=backend/tests/chat` зелёный.
- Контракт § Контракты (SSE): `title_updated { title }` — не-терминальное событие; состав и семантика терминальных событий (`done` / `error` / `security_block`) и wire-формат не изменились.
- Решения брифа § Доставка title: при первом событии `security_block` генерация не запускается (заблокированный текст не уходит в title-LLM); блокировка *после* старта задачи не мешает генерации, но запись отсекается перечиткой `ThreadView` из T1.4; если задача не успела до конца рана, события нет и стрим закрывается штатным `done` (fallback-инвалидацию делает фронт — трек T2).

## Cross-cutting

После всех фаз трека:

- `make check` и `make test-scope P=backend/tests` — зелёные (per-track гейт из § Партиция треков).
- Все строки таблицы § Контракты, относящиеся к бэкенду, реализованы: `POST /chats` без тела; `PUT /chats/{id}` → `200`; `DELETE /chats/{id}` → `204` идемпотентный; SSE `title_updated`; обязательная секция `title` в `agent.yaml`; промпт `title--{development,production}` + `configs/prompts/title.txt`; новая env-переменная таймаута.
- Схема БД не менялась — новых Alembic-миграций в диффе трека нет (§ Персистентность).
- Файловый скоуп не нарушен: диффа нет в `frontend/**`, `doc/**`, `packages/testing/**`, `backend/tests/conftest.py`, `Makefile`; правки чужих тест-файлов ограничены перечисленными в T1.3 и сводятся к добавлению секции `title` (плюс `delete_thread` у фейка runner'а в `backend/tests/chat/conftest.py` — файл внутри тест-скоупа трека).
- Логирование по конвенции: `structlog` keyword-args, `warning` + `exc_info=True` на деградациях (title-генерация, `adelete_thread`), `info` на успешной генерации.
- Ручные сквозные проверки (живой SSE `title_updated`, оба пути входа, rename/delete против реального API) — вне трека, прогоняются на INTEGRATION_TEST после барьера. Актуализация `streaming.md` / `backend.md` / `agent-runtime.md` / `prompt-management.md` — фаза DOC_UPDATE.

## Open Questions

Открытых вопросов нет — оба закрыты решением архитектора (эскалация оркестратора, 2026-07-27):

1. ~~Числовое значение лимита длины названия~~ — **решено: 100** (по прецеденту `RegisterRequest.name`, `MCPServerCreate.name`, `maxLength={100}` во фронте). Константа общая: `ChatUpdate.title`, усечение auto-title, дрейф-фикс `ProjectUpdate.name`; трек T2 использует то же значение в `maxLength` rename-диалога.

2. ~~`.env.local.example` для `LLM_TITLE_TIMEOUT_SECONDS`~~ — **решено: три места по прецеденту `LLM_IMAGE_TIMEOUT_SECONDS`** (`Settings`, `.env.example`, `docker-compose.yml`). Уточнение конвенции («`.env.local.example` — только для реально переопределяемых local-значений») уходит кандидатом в harvest.
