# Implementation Plan: feat-011 / трек T1 — Backend: файловый workspace, переезд артефактов, инструменты агента

## Контекст

Трек T1 переводит backend с PG-модели артефактов на файловый workspace проекта и даёт агенту новую поверхность инструментов — файловые операции и исполнение кода через executor. Конкретно: появляется файловый слой (два корня, канонизация путей, атомарная запись, снапшот зоны `artifacts/`), артефакт становится файлом с путём вместо UUID (REST переезжает на path-query, таблицы `artifacts`/`artifact_blobs` дропаются, связь «артефакт ↝ чат» переезжает с PG-колонки `message_id` на typed part `ArtifactPart` в чекпоинте), набор инструментов пополняется пятёркой `read_file`/`write_file`/`list_files`/`execute_code`/`run_command` при упразднении `create_artifact`, и появляются вложения пользователя (`POST /uploads` + пометка в user-сообщении + metadata для UI-чипа). Плюс инфраструктурная обвязка: единый uid 10001 для backend-образа, том `workspaces`, ro-mount `/skills`, сеть `exec` и блок executor-сервиса в compose.

Источники (читать до старта фазы, не по памяти):

- Запись итерации — `doc/tasks/tasklist-dogfooding.md` § feat-011 (L)
- `doc/tasks/iterations/dogfooding/feat-011-execution-runtime/design-brief.md` — полная картина; границы трека — § Партиция треков (строка T1), политика `uv.lock` и межтрековые контракты 1–7 там же
- `doc/tasks/iterations/dogfooding/feat-011-execution-runtime/acceptance.md` — сквозные сценарии A/B/C, на которые ссылается verification фаз
- `doc/tech/adr/ADR-031-execution-runtime-isolation.md`, `doc/tech/adr/ADR-032-project-workspace-file-model.md`
- `doc/tech/streaming.md` (SSE-контракт, typed parts истории), `doc/tech/agent-runtime.md` (инструменты, скиллы, субагенты), `doc/tech/backend.md` (слои, REST, персистентность)
- Конвенции: `doc/tech/conventions.md` (ядро: env-workflow «четыре места», логирование, именование Repository vs Storage), `doc/tech/conventions/db.md` (миграции — только autogenerate), `doc/tech/conventions/api.md` (Annotated-стиль, list envelope, problem+json), `doc/tech/conventions/agent.md` (чек-лист «добавляешь инструмент», sentinel `_NO_RUNTIME` для `ToolRuntime`), `doc/tech/conventions/testing.md`
- Спайк `spikes/spike-bwrap-gvisor.md` — читать ради следствия №2 (владелец каталога = uid джобы ⇒ все `mkdir` делает backend)

### Границы трека и что в них не входит

Файловый скоуп T1 (владение на запись): `backend/**`, `configs/**`, `packages/siem-contracts/**`, `services/siem-service/Dockerfile` (только строки bind-mount манифеста executor), `docker-compose.yml`, `.env.example`, `.env.local.example`, `.gitignore`/`.dockerignore`.

Вне скоупа T1 — не трогать даже при соблазне:

- `frontend/**` (T2), `services/executor/**` и `Makefile` и корневой `pyproject.toml` и `uv.lock` (T3), `doc/**` (DOC_UPDATE после барьера), `tools/**`, `.pre-commit-config.yaml`, `.github/**`.
- **Манифесты зависимостей в per-track фазах не трогаются** (политика «один писатель `uv.lock`»). Практические следствия для T1: `pdfkit`/`markdown`/`python-markdown-math` остаются в `backend/pyproject.toml` и их mypy-overrides — в корневом `pyproject.toml`, хотя импортов после T1.7 не останется; `python-multipart` под `UploadFile` приезжает транзитивно через `mcp` и явно **не** объявляется. Уборка — отдельной фазой после барьера, чужими руками.
- Регенерация фикстуры делается командой из `conventions/agent.md` (`PYTHONPATH=backend uv run --package learnflow-backend python scripts/generate_tool_names_fixture.py` из корня) — make-цели для неё нет и заводить её нельзя (`Makefile` — файл T3).

### Политика по тест-файлам

Автотесты трека пишет независимый `test-author` — implementer их не авторит и не подгоняет ассерты под реализацию. Единственное исключение, без которого фазы физически не сходятся: **тесты и фикстуры упразднённой функциональности удаляются вместе с ней** (файл целиком либо дохлая фикстура), потому что они ссылаются на удалённые модели/сервисы и роняют коллекцию pytest. Правка ассертов выжившего поведения — не работа implementer'а; если тест краснеет не из-за удаления, а из-за смены контракта, это фиксируется в `summary.md` для `test-author`, а не правится на месте. Файлы, которые точно уйдут вместе с кодом, перечислены в фазах. См. также Open Question OQ-1.

## Фазы

### T1.1: Файловый слой workspace, Settings-knobs, словарь security-событий

**Цель:** появляется единственная точка работы с файлами проекта — резолв путей против двух корней, чтение/атомарная запись/листинг и снапшот зоны `artifacts/`; никаких потребителей у неё пока нет.

**Изменения:**

- `backend/app/storage/workspace.py` (новый; рядом с `blob_storage.py`, по правилу § Именование это Storage, не Repository) — резолв пути от агента/REST против корней `<workspaces_root>/{project_id}` (rw) и `<skills_root>` (ro): канонизация `resolve()` → `is_relative_to()` **по канонизированному пути**; `write` разрешён только в workspace, `/skills` — ro. Отказ — доменное исключение файлового слоя (не `HTTPException`, § Обработка ошибок → доменные исключения) + security-лог `logger.warning(..., security_event=True, event_type=AGENT_RUNTIME_PATH_DENIED, severity=...)`. Операции: чтение текста с лимитом и пометкой усечения, отказ на бинаре («binary file, use media endpoint» — прецедент `load_skill`), запись `tmp + rename` (tmp — в целевой директории, узнаваемый префикс), `parents=True` на запись, нерекурсивный листинг + флаг рекурсии, скрытие tmp-файлов из листинга. Отдельно — снапшот зоны `artifacts/` по `(path, mtime, size)` + before-копия содержимого текстовых файлов в память под два лимита (per-file и суммарный на джобу; превышение любого → дельта `null`), и diff двух снапшотов в список `{path, kind: created|updated, diff: {added, removed} | null}`. Плюс хелперы, нужные соседям: `path` артефакта = путь относительно `artifacts/` без префикса; **`type` артефакта = расширение файла без точки** (`md`, `png`, …) — единая семантика для конверта SSE, `ArtifactPart` и REST (бриф § Метаданные: семантический `"image"` уходит, категорию вьюера определяет фронт словарём расширений); санитайз имени файла (basename, вычистка слэшей и управляющих, unicode сохраняется, пустой результат → generated-имя, коллизия → числовой суффикс); mime → расширение. Форма элемента листинга — относительный путь + признак файл/директория (бриф § Контракты). `project_id` — параметр слоя, не инструмента.
- `backend/app/config.py` — knobs: корни `workspaces_root` / `skills_root`, лимит чтения файла, два лимита diff-копии, лимит размера upload, URL executor и deadline джобы + запас клиентского таймаута (последние два понадобятся с T1.4, но объявляются здесь одним заходом, чтобы «четыре места» синхронизировались один раз). Дефолты — dev-дружественные.
- `packages/siem-contracts/siem_contracts/vocabulary.py` + `__init__.py` — константа `AGENT_RUNTIME_PATH_DENIED = "agent.runtime.path_denied"` в блоке `# Agent runtime events`, тот же литерал в `EventType`, реэкспорт в `__all__` (иначе краснеет `packages/siem-contracts/tests/test_vocabulary.py`).
- `.env.example`, `.env.local.example`, `docker-compose.yml` — те же knobs (жёсткое правило «четыре места»). В compose: именованный том `workspaces`, смонтированный в `app`; `./skills` перевешивается на `/skills:ro` (сейчас `./skills:/app/skills:ro`) — по § Скиллы путь единый для обоих контейнеров. В `.env.local.example` — локальные корни для `make dev` (в host-режиме `/workspaces` и `/skills` не существуют).
- `backend/Dockerfile` — `COPY skills/ /app/skills/` → `/skills/` (парная правка к смене пути; строка bind-mount манифеста executor придёт в T1.10).
- `backend/app/main.py` — `skills_dir` перестаёт быть константой кода (`Path(__file__).parents[2] / "skills"`), берётся из `Settings`.
- `.gitignore` — локальный корень workspaces для dev-режима.

**Verification:**

- `make check` проходит (в т.ч. `lint-imports` и `arch_checker`: новый модуль в `app/storage/` не должен нарушать слоевые контракты — корневой `pyproject.toml` вне скоупа, править контракты нельзя; нарушение = эскалация).
- `make test-contracts` зелёный — интегритет словаря (Literal ⇔ константы ⇔ `__all__`, 3-сегментный regex) держится на новом типе события.
- `make test` не краснеет от этой фазы (потребителей у слоя ещё нет; `backend/tests/security/test_event_vocabulary_contract.py` проверяет producer ⊆ vocabulary — направление, которое добавление типа не ломает).
- Контракты, на которые фаза работает: acceptance B6 (отказ резолва + security-лог `agent.runtime.path_denied`), B7 (`/skills` ro), A7 (персистентность workspace).

### T1.2: Конверт-список артефактов, `artifact_updated`, `ArtifactPart` в истории, снос PG-привязки к сообщению

**Цель:** связь «артефакт ↝ чат» переезжает с PG-колонки `message_id` на typed part чекпоинта, а канал SSE учится отдавать N событий на вызов и различать создание и обновление.

**Изменения:**

- `backend/app/agent/stream_events.py` — `artifact_created_envelope` превращается в генерацию **списка** конвертов из `ToolMessage.artifact` (теперь список, а не dict); каждый элемент несёт признак created/updated и, для updated, дельту `{added, removed}`; тип события — `artifact_created` / `artifact_updated`; wire-имя типа файла — `artifact_type`, **значение — расширение файла без точки** (не семантический `"image"`; см. хелпер T1.1) (ключ `type` затёр бы тип события в плоском конверте `messages.py`). `make_tool_result_reporter` эмитит N конвертов сразу за `tool_result` своего вызова, в том же per-call flow за guard'ом TOOL_RESULT.
- `backend/app/agent/tools/artifacts.py`, `backend/app/agent/tools/image_generation.py` — возврат артефакта приводится к списку из одного элемента (одна строка на инструмент; переезд `generate_image` на файлы — T1.7, здесь только форма конверта).
- `backend/app/agent/runner.py` (диспетчер custom-канала, passthrough lifecycle-типов) — `artifact_updated` добавляется в проброс наряду с `artifact_created`.
- `backend/app/services/agent_runner.py` — новый frozen dataclass `ArtifactPart {path, title, type, kind, diff?}` рядом с `ReasoningPart`/`TextPart`/`ToolCallPart` (§ Типизация: внутренние value-объекты рантайма — dataclass).
- `backend/app/agent/checkpoint_history.py` — при реплее чекпоинта из `ToolMessage.artifact` выводится `ArtifactPart` (по одному на элемент списка), встраивается в последовательность parts хода. Это единственное место, знающее форму `channel_values["messages"]` (`conventions/agent.md`) — разбор туда и идёт.
- `backend/app/api/schemas/chats.py` — `ArtifactPartOut` в дискриминированный union `MessagePartOut`; поле `MessageOut.artifacts` убирается.
- `backend/app/api/routes/chats.py` — группировка `artifacts_by_msg` и вызов `artifact_service.list_by_thread` уходят; `_part_out` покрывает новый тип.
- `backend/app/services/chat.py` — сбор `artifact_ids` по событию и post-hoc `set_message_id` уходят; множество допустимых типов событий пополняется `artifact_updated` (его пинит `backend/tests/chat/test_chat_service.py`).
- `backend/app/repositories/artifact.py` — `set_message_id` и `list_by_thread` удаляются (мёртвый код; сам репозиторий доживёт до T1.7).
- Удаление тестов упразднённого: `backend/tests/chat/test_chat_service.py::test_send_message_links_created_artifacts_to_message` и фейк `FakeArtifactRepo.set_message_id`-часть в `backend/tests/chat/conftest.py`.

**Verification:**

- `make check`, `make test` зелёные (кроме удалённого выше).
- Ручная проверка формы провода не требуется на этой фазе — покрывается A6/A6b на интеграции; здесь достаточно, что `artifact_created` продолжает уходить со старых инструментов в новой форме payload (`path` появится в T1.3, пока `id`).
- Контракт для T2 (фиксирован брифом, расхождения ловит INTEGRATION_TEST): `ArtifactPart` в `parts`, `artifact_updated` с `artifact_type` и дельтой.

### T1.3: Файловые инструменты `read_file` / `write_file` / `list_files`; `create_artifact` упраздняется

**Цель:** агент получает явные файловые операции, а запись артефакта перестаёт быть отдельной сущностью — это просто запись файла в `artifacts/`.

**Изменения:**

- `backend/app/agent/tools/files.py` (новый) — три инструмента поверх файлового слоя. `project_id` берётся из `AgentContext` (`runtime.context`), параметром не выставляется. Аннотация инжектируемого параметра — **ровно** `ToolRuntime` с модульным sentinel `_NO_RUNTIME` и явной веткой `if runtime is None` (`conventions/agent.md`; прецеденты `user_memory.py`, `skill_context.py`). `read_file`/`list_files` работают с обоими корнями, `write_file` — только workspace. `write_file` возвращает `response_format="content_and_artifact"` со списком из одного элемента **только когда путь попал в зону `artifacts/`**; created/updated различается по факту существования файла, дельта — по прочитанному перед перезаписью старому содержимому; `title` = имя файла, `type` = расширение (хелперы T1.1) — то же в элементах diff-снапшота джобы (T1.4).
- `backend/app/agent/tools/artifacts.py` — удаляется целиком (`create_artifact` покрыт `write_file`).
- `backend/app/agent/tools/registry.py`, `backend/app/agent/tools/__init__.py`, `backend/app/main.py` — реестр и wiring: три новых имени внутрь, `create_artifact` наружу (сигнатура `assemble_internal_tools` теряет параметр).
- Удаление тестов упразднённого: тесты `create_artifact` (в т.ч. соответствующие кейсы `backend/tests/agent/test_stream_events.py`, если они завязаны именно на этот инструмент, а не на конверт).

**Verification:**

- `make check`, `make test` зелёные.
- `PYTHONPATH=backend uv run --package learnflow-backend python scripts/generate_tool_names_fixture.py` **пока не запускать** — фикстура фиксируется одним заходом в T1.5, чтобы T2 не пересобирал реестр подписей дважды. Соответственно `backend/tests/agent/test_tool_names_fixture.py` на этой фазе красный — ожидаемо и допустимо только до T1.5 (зафиксировать в `summary.md`).
- Контракты: A3 (`write_file` → `artifacts/` → `artifact_created`), A6 (перезапись → `artifact_updated` с дельтой), B6 (`read_file /etc/passwd` → отказ + security-лог).

### T1.4: Клиент executor, инструменты `execute_code` / `run_command`, diff-снапшот зоны `artifacts/`

**Цель:** агент получает исполнение кода и bash в workspace через соседний сервис, а появившиеся после джобы файлы превращаются в события артефактов без участия executor.

**Изменения:**

- `backend/app/infra/executor.py` (новый) — тонкий httpx-клиент к `POST /jobs` по контракту `{project_id, code|cmd, timeout} → {stdout, stderr, exit_code}` (межтрековый контракт 2, фиксирован в § Executor брифа; `execute_code` идёт веткой `cmd` — backend сам пишет файл, резолюция OQ T3-1). Иерархия таймаутов (согласовано с `tracks/T3/plan.md` § knobs): deadline джобы — knob `Settings`, **дефолт ≤ `EXECUTOR_MAX_TIMEOUT_SECONDS` (300)** — иначе executor молча клампит; client-timeout = deadline + фиксированный запас, **запас ≥ `EXECUTOR_KILL_GRACE_SECONDS` (5 с) + люфт** — ответ на таймаут джобы приходит через deadline + kill-grace, меньший запас превращал бы каждый таймаут в ложный «runtime unavailable». Транспортные отказы (connect refused, HTTP-таймаут) ловятся **узким** классом httpx-ошибок и возвращаются in-band формулировкой «execution runtime unavailable — инфраструктурная проблема, не ошибка кода», чтобы агент не уходил чинить код; прочие исключения — обычный `handle_tool_error`.
- `backend/app/agent/tools/execution.py` (новый) — `run_command(cmd)` и `execute_code(code)`; `execute_code` — специализация: код пишется во временный файл в workspace через файловый слой (тот же tmp-префикс, что у атомарной записи — скрыт из `list_files` и из снапшота), в команде джобы адресуется **относительным путём от cwd** (абсолютный backend-путь внутри mount-ns джобы не существует), удаляется в `finally`. Обвязка сама гарантирует существование workspace (`mkdir(parents=True, exist_ok=True)` перед `POST /jobs`) — **все mkdir на стороне backend**, это требование единого uid из спайка, а не удобство. Вокруг вызова — снапшот зоны `artifacts/` до и после, diff → список `ArtifactPart`-совместимых элементов в конверте `content_and_artifact`. Результат джобы (ненулевой exit, таймаут) — обычный `ToolMessage` со stderr, не исключение; усечение по `text_limits`.
- Langfuse — в спан tool-вызова джобы кладутся `exit_code` и длительность (образец ручной обсервации — `image_generation.py`); LLM-стоимости у джобы нет.
- `backend/app/agent/tools/registry.py`, `__init__.py`, `backend/app/main.py` — регистрация двух имён и wiring клиента.

**Verification:**

- `make check` проходит; `make test` зелёный (executor в per-track тестах фейкуется, живой связки здесь нет).
- Контракты: A1 (`execute_code` со статистикой по CSV), A2 (`run_command`, версия pandoc), A4 (matplotlib → png через diff-снапшот), A10 (падение джобы = рабочий цикл, тред жив), A12 (извлечение текста из PDF через джобу). B2/B3/B5/B8 проверяются на живой топологии (INTEGRATION_TEST), не здесь.

### T1.5: Фиксация поверхности инструментов — `load_skill`, `run_subagent`, промпты/конфиги, фикстура имён

**Цель:** набор и семантика инструментов становятся окончательными, фикстура имён регенерируется один раз — это точка, после которой T2 может гнать свои тесты реестра подписей.

**Изменения:**

- `backend/app/agent/tools/skills.py` — `load_skill` меняет реализацию, сохраняя семантику 1:1: чтение `SKILL.md`, автосписок файлов скилла и валидация путей идут через файловый слой поверх корня `/skills` (из `Settings`), индекс skill-context из Store остаётся как есть. `scan_skills_index` / `scan_skill_names` — тот же корень.
- `backend/app/agent/tools/subagents.py` — вход меняется с UUID на пути: артефакты резолвятся файловым слоем (скоуп по `project_id` из контекста), поведение «всё или ничего» и XML-обёртка `document` сохраняются; параметр переименовывается (`input_artifact_ids` → `input_artifact_paths`), description переписывается (`create_artifact` → `write_file`). Субагентам файловых инструментов в v1 не выдаём.
- `configs/prompts/system.txt` — `<internal_tools>` (перечень способностей: файловые операции и исполнение кода вместо «artifact creation») и `<artifacts_guidelines>` (артефакт = файл в `artifacts/`, а не вызов `create_artifact`).
- `configs/agent.yaml` — описания субагентов `judge` и `web-research`: «artifact id(s)» → пути артефактов.
- `configs/security.yaml` — формулировка `tool_call_arg.description` про «persisted into artifacts/memory» приводится к файловой модели (правка текстовая, семантика чекпоинта не меняется).
- `backend/contracts/agent-tool-names.json` — регенерация фикстуры указанной выше командой (файл руками не редактируется).
- `backend/scripts/seed_demo.py` — снятие зависимости от `create_artifact`/`Artifact`, если сидер её несёт (полностью — в T1.9 вместе с моделями; здесь — только то, что ломает импорт).

**Verification:**

- `make check`, `make test` зелёные — в том числе `backend/tests/agent/test_tool_names_fixture.py` (drift-гейт снова зелёный: фикстура == сгенерированному).
- Фикстура содержит ровно `read_file`, `write_file`, `list_files`, `execute_code`, `run_command` сверх прежнего набора и **не** содержит `create_artifact`.
- **Оркестратору:** после локального коммита этой фазы можно пускать GREEN/TEST трека T2 по реестру подписей (межтрековый контракт 1). Отдельно донести до T2 переименование параметра `input_artifact_ids` → `input_artifact_paths` — если запись реестра подписей читает имена аргументов, она поедет.
- Контракты: A9 (ход со скиллом: `load_skill` поверх файлового слоя + skill-context), C1 (`run_subagent` на путях).

### T1.6: REST артефактов на файловую модель

**Цель:** четыре GET-эндпоинта сохраняют семантику, но адресуются путём в query-параметре и читают файлы; PDF-путь снимается.

**Изменения:**

- `backend/app/api/routes/artifacts.py` — `list` (без `path`, рекурсивный обход зоны `artifacts/`, сортировка по `updated_at` — бриф § Метаданные), `get` (`?path=`), `media` (`?path=`), `download` (`?path=`, без `format`). `media`: `ETag` / `Last-Modified` из `(mtime, size)` + `Cache-Control: no-cache`, обработка `If-None-Match` → 304; `X-Content-Type-Options: nosniff` остаётся. Detail бинарного файла отдаёт метаданные без `content`. `format=pdf` и весь wkhtmltopdf-путь не переносятся. Ownership — существующая зависимость `UserProject`, ручных проверок не добавлять (`conventions/api.md`).
- `backend/app/api/schemas/artifacts.py` — `id: UUID` → `path: str`; `type` = расширение файла (хелпер T1.1); `updated_at` (mtime) вместо `created_at`; из detail уходят `thread_id`/`message_id`. Envelope списка — существующий `Page[T]` (`{items, total, limit, offset}`), см. OQ-2.
- Осиротевший knob `pdf_conversion_timeout_seconds` снимается во всех четырёх местах (`backend/app/config.py:68`, `.env.example:66`, `.env.local.example`, `docker-compose.yml:85`) — грепы cross-cutting его не ловят (имя не содержит `pdfkit`/`wkhtmltopdf`); манифестов зависимостей это не касается, политика `uv.lock` не нарушается.
- `backend/app/api/deps.py` — зависимость файлового слоя вместо `ArtifactServiceDep`; `BlobStorageDep` пока живёт (уходит в T1.7).
- `backend/app/api/export.py` — удаляется (единственный потребитель — снятая ветка `format=pdf`).
- Удаление тестов упразднённого: `backend/tests/projects/test_artifacts_api.py::test_download_pdf_branch_converts_via_export` и прочие кейсы, завязанные на UUID-адресацию и PG-контент (файл `test_artifacts_api.py` переписывается `test-author`'ом под новый контракт — implementer удаляет то, что не может пройти по построению, и фиксирует список в `summary.md`).

**Verification:**

- `make check`, `make test` зелёные (с учётом удалений).
- Контракты: A5 (артефакт в поддиректории открывается, list показывает вложенность), C3 (list/detail/media/download на путях, detail бинарного — без `content`), A6 в части ETag-ревалидации media.

### T1.7: `generate_image` пишет файл; снос PG-цепочки артефактов

**Цель:** последний писатель в `artifact_blobs` переезжает на файлы, и вся сервисно-репозиторная цепочка PG-артефактов исчезает.

**Изменения:**

- `backend/app/agent/tools/image_generation.py` — результат вызова image-модели кладётся файлом в `artifacts/`: имя = слаг от `title` (unicode сохраняется, вычищается недопустимое для ФС; пустой результат → fallback `image-N`; коллизия → числовой суффикс) + расширение из mime ответа; запись `tmp + rename` после успешного ответа API вместо PG-транзакции. **`type="image"` уходит**: в конверт и `ArtifactPart` идёт итоговое имя файла как `title` и расширение как `type` (модельный заголовок — только сырьё для слага; иначе подпись карточки в ленте разошлась бы со строкой REST-списка того же файла). Колонка-дом для промпта исчезает — промпт виден в аргументах вызова в ленте и в Langfuse. По ленте/SSE идёт тем же путём, что остальные артефакты (конверт-список из T1.2).
- Удаляются: `backend/app/services/artifact.py` (`ArtifactService`), `backend/app/repositories/artifact.py` (`ArtifactRepository`), `backend/app/storage/blob_storage.py` (`BlobStorage` + `PgBlobStorage`); соответствующие строки в `backend/app/services/__init__.py`, `backend/app/repositories/__init__.py`, `backend/app/api/deps.py` (`ArtifactServiceDep`, `BlobStorageDep`, аргумент `artifact_repo` у `get_chat_service`), `backend/app/main.py`.
- Удаление тестов упразднённого: `backend/tests/projects/test_artifact_repository.py`, `backend/tests/projects/test_artifact_service.py`, `backend/tests/image_generation/test_blob_storage.py`, `FakeArtifactRepository` в `backend/tests/projects/fakes.py`, соответствующие фикстуры в `backend/tests/chat/conftest.py`; кейсы `test_generate_image_*` про атомарность блоба (заменяются кейсами про файл, авторит `test-author`).

**Verification:**

- `make check`, `make test` зелёные.
- Контракты: C1 (`generate_image` пишет файл, механика вызова не изменилась), A4/A5 (картинка-артефакт открывается по пути через media).

### T1.8: Вложения пользователя — `POST /uploads`, пометка в сообщении, metadata

**Цель:** файл, прикреплённый пользователем, доезжает до `uploads/` в момент отправки сообщения, модель видит пометку с путями, UI получает metadata для чипа.

**Изменения:**

- `backend/app/api/routes/uploads.py` (новый) — `POST /projects/{project_id}/uploads`, multipart, один файл за запрос, ответ `{path: "uploads/<name>"}`. Ownership — существующая зависимость `UserProject` (как в T1.6): это единственный новый write-эндпоинт, кладущий файлы в workspace. Запись — через файловый слой, только в зону `uploads/`; имя = санитайзнутый basename, коллизия → числовой суффикс (повторная загрузка не перезаписывает файл, на который смотрит metadata старого сообщения). Лимит размера — knob `Settings`, превышение → problem+json (`conventions/api.md`), 201 на создание. REST-чтения `uploads/` нет — только POST.
- `backend/app/main.py` — подключение роутера.
- `backend/app/api/schemas/messages.py` (тело запроса — `MessageCreate`) + `backend/app/api/routes/messages.py` — запрос отправки сообщения принимает `attachments: list[str]` (пути, выданные upload'ом).
- Нитка `attachments` тянется через всю цепочку: `backend/app/services/chat.py` (`ChatService.send_message`) → `backend/app/services/agent_runner.py` (сигнатура `stream`) → `backend/app/agent/runner.py` (сборка `HumanMessage`, строка ~193). **Backend** формирует пометку «[Прикреплены файлы: …]» и дописывает её к тексту для модели (он единственный знает канонический путь); в `additional_kwargs` `HumanMessage` кладётся чистый пользовательский текст и `attachments: [{path, title}]` — история самоописывается симметрично `ArtifactPart`.
- `backend/app/agent/checkpoint_history.py` + `backend/app/api/schemas/chats.py` — `MessageOut` отдаёт чистый текст и `attachments` отдельными полями; пометку видит только модель, дубля «чип + та же строка текстом» в UI нет.
- `configs/prompt_fragments.yaml` — шаблон пометки (по прецеденту XML-обёртки `document` для субагентов: модель-facing строки живут в конфиге, не в коде).

**Verification:**

- `make check`, `make test` зелёные.
- Контракты: A11 (прикреплённый `.md` прочитан агентом), A12 (PDF → извлечение через джобу), A13 (чип в истории после перезагрузки — из metadata), A14 (превышение лимита → внятная ошибка).
- Отдельно проверить, что `UploadFile` работает без явного объявления `python-multipart` (приезжает транзитивно через `mcp`) — если нет, это **эскалация оркестратору**, а не правка манифеста (политика `uv.lock`).

### T1.9: Drop-миграция таблиц, снятие ORM-моделей, lifecycle workspace

**Цель:** схема БД избавляется от `artifacts`/`artifact_blobs`, а workspace получает жизненный цикл проекта.

**Изменения:**

- Удаляются `backend/app/models/artifact.py`, `backend/app/models/artifact_blob.py`; реэкспорты в `backend/app/models/__init__.py`; обратные связи `Project.artifacts` (`backend/app/models/project.py`) и `ThreadView.artifacts` (`backend/app/models/thread_view.py`) вместе с их TYPE_CHECKING-импортами.
- `backend/alembic/versions/<new>.py` — **только `alembic revision --autogenerate` против запущенной БД** (жёсткое правило проекта, `conventions/db.md`): `make docker-up-db` → `make migrate` → удалить модели → `make migration msg="drop artifacts and artifact_blobs"` → прочитать сгенерированный файл → `make migrate`. Down_revision — текущий head `05b404b12f90`. Ручная миграция здесь не допускается: данные не мигрируются (личный догфудинг), поэтому autogenerate покрывает случай полностью.
- `backend/app/services/project.py` (`ProjectService.delete_project` — сейчас чистит полиморфные MCP-disables и удаляет строку, артефакты уходили DB-каскадом) — добавляется удаление директории workspace проекта; создание workspace — ленивое, при первом обращении (гонка «удалили проект, живой ран пересоздал директорию» принята, порядок «отменить раны при delete» не вводится).
- `backend/scripts/seed_demo.py` — снятие сидинга артефактов в PG (решение OQ-3: артефактная часть вырезается, проекты/чаты остаются; перевод на файлы — follow-up).
- Удаление тестов упразднённого: `ArtifactFactory` в `backend/tests/projects/conftest.py`, артефактные ветки `backend/tests/projects/test_thread_view_repository.py`, `backend/tests/image_generation/test_media_endpoint.py` (переписывается под path-адресацию `test-author`'ом), артефактный харнесс `backend/tests/subagents/conftest.py`.

**Verification:**

- `make check`, `make test` зелёные.
- **Страж дрейфа:** повторный `make migration msg="drift-check"` даёт пустую миграцию (файл удалить); это же проверяет автотест-страж в `backend/tests/`.
- **Чистая БД:** `docker compose down -v` → `make docker-up-db` → `make migrate` проходит с нуля.
- `downgrade -1` новой ревизии применим (правило проверки отката критичных ревизий, `conventions/testing.md`).
- Контракт: C2 (удаление проекта сносит директорию workspace).

### T1.10: Backend-образ на non-root uid 10001, bind-mount манифеста executor

**Цель:** app, executor и джоба работают под одним uid (требование gVisor из спайка), а оба существующих образа знают о новом workspace-члене.

**Изменения:**

- `backend/Dockerfile` — non-root пользователь с uid/gid **10001** (межтрековый контракт 4): создание пользователя, владение `/app/.venv` и `/app` (образ сейчас целиком под root), `USER` перед entrypoint. Проверить, что `uv run` и `alembic` из `backend/entrypoint.sh` работают под non-root (`UV_NO_SYNC=1` уже стоит; кэш uv не должен уезжать в `/root`).
- `backend/entrypoint.sh` — правки, если non-root ломает текущую последовательность (alembic → uvicorn).
- `backend/Dockerfile` и `services/siem-service/Dockerfile` — добавить `--mount=type=bind,source=services/executor/pyproject.toml,target=services/executor/pyproject.toml` в блок манифестов перед `uv sync --locked` (иначе резолв workspace падает), и в siem-Dockerfile — `COPY`-строку манифеста по образцу существующего `COPY backend/pyproject.toml`. В `services/siem-service/Dockerfile` **только эти строки** — файл принадлежит T1 именно в этой узкой части.
- `docker-compose.yml` — `user: "10001:10001"` для `app`.
- `.dockerignore` — правки только если что-то мешает новым mount/COPY.

**Verification:**

- `make check` (кода не касается — гейт формальный).
- `docker compose build` на этой фазе **зелёным быть не обязан**: правка парная с регистрацией `services/executor` как workspace-члена (T3, межтрековый контракт 6), сборка проверяется на INTEGRATION_TEST. Не «чинить» это добавлением члена в корневой `pyproject.toml` — файл чужой.
- Контракты: B5 (процесс в контейнере non-root), B6c (запись в свой workspace из джобы — единый uid), проверяются на INTEGRATION_TEST.

### T1.11: Compose-wiring executor-блока и сети `exec`

**Цель:** топология собирается: executor поднимается отдельным сервисом в изолированной сети, app видит его и только его.

**Предусловие:** оркестратор передал точный список `EXECUTOR_*`-knobs и параметров контейнера из `tracks/T3/plan.md` (межтрековый контракт 5). Без него фаза не стартует — содержимое блока предметная область T3.

**Изменения:**

- `docker-compose.yml` — сервис `executor`: `build.context: .`, `dockerfile: services/executor/Dockerfile`, `runtime: runsc`, `cpus` / `mem_limit` / `pids_limit`, `stop_grace_period` ≥ deadline джобы, healthcheck по образцу siem (`curl -f http://localhost:<port>/health`, `start_period: 30s`), `logging` как у остальных, монтирование тома `workspaces` и `./skills:/skills:ro`, `user: "10001:10001"`, **порт наружу не публикуется**. **`security_opt: [seccomp=unconfined, apparmor=unconfined, systempaths=unconfined]`** (решение архитектора, эскалация 2026-08-11): под дефолтным docker-профилем bwrap не может создать userns и примонтировать `/proc` (masked paths) — без этих опций слой 3 (bwrap per job) не работает вообще; граница executor — gVisor (прод, `runtime: runsc`) + bwrap, не seccomp/apparmor контейнера — комментарий в compose обязателен, фиксация в ADR-031 на DOC_UPDATE. Env-блок — явно по переменной (`${VAR:-default}`), blanket `env_file` не использовать. Сети: новая `exec` с `internal: true`; `executor` — **только** в ней; `app` — в `default` и `exec`; остальные сервисы не трогать (сейчас у сервисов ключа `networks` нет вовсе — придётся проставить `default` там, где появляется явный список, чтобы не выпасть из стековой сети).
- `.env.example` — секция `# ───────── Executor ─────────` по образцу SIEM-секции (рамка, комментарий на knob про дефолт/прод/рестарт); `.env.local.example` — только отличающиеся значения; зафиксировать в комментарии, что в local-dev режиме (`make dev`) executor не поднят и `execute_code`/`run_command` недоступны.

**Verification:**

- `docker compose config` валиден; `docker compose config` показывает `executor` только в сети `exec`, `app` — в обеих.
- Живая проверка — INTEGRATION_TEST: B1 (в env executor нет `DATABASE_URL`/`JWT_SECRET`/LLM-ключей), B2 (нет DNS/маршрута до `db`/`redis`), B3 (нет egress и `app:8000`), B4 (тулчейн на месте), B5 (`docker inspect` → `runsc`, non-root), B8 (deadline + kill-цепочка), B9 (стоп во время джобы).

## Cross-cutting

После всех фаз трека, до барьера:

- `make check` и `make test` зелёные целиком; `make test-contracts` зелёный.
- Миграции применяются на чистой БД: `docker compose down -v` → `make docker-up-db` → `make migrate`; повторный autogenerate пуст (нет дрейфа модель ↔ миграции).
- Фикстура `backend/contracts/agent-tool-names.json` соответствует реестру (drift-гейт зелёный), состав инструментов совпадает с таблицей § Инструменты агента брифа.
- Ни одного упоминания `artifacts`/`artifact_blobs`/`BlobStorage`/`pdfkit`/`wkhtmltopdf` в коде `backend/app/**` (грепом); остаточные записи в манифестах зависимостей — сознательно, уборка после барьера.
- Env-переменные синхронны в четырёх местах (`Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml`) — пройтись глазами по итоговому списку knobs один раз.
- Все `mkdir` каталогов workspace делает backend (нигде не появилось «executor создаст сам») — предпосылка единого uid из спайка.
- `summary.md` трека несёт: список удалённых тест-файлов и причину каждого удаления (для `test-author` и ревьюеров), решение по неймингу `input_artifact_paths`, решение по судьбе `seed_demo.py`, допущение «один uvicorn-воркер» как пункт для docs-updater (OQ-5).
- Не покрывается T1 и уходит на INTEGRATION_TEST: сборка образов (парная правка с T3), живая связка с executor, вся секция B acceptance.

## Open Questions

Все вопросы закрыты на эскалации 2026-08-11 (оркестратор + архитектор), открытых нет.

- **OQ-1. Граница «implementer не трогает тест-файлы» при сносе функциональности.** ~~Нужно подтверждение трактовки.~~ **Закрыто (оркестратор):** трактовка плана подтверждена — implementer удаляет тесты/фикстуры упразднённой функциональности целиком в фазе, где сносит их предмет (иначе падает pytest-коллекция), и не правит ассерты выжившего поведения; список удалений с причинами — в `summary.md`; дифф тронутых тест-файлов — предмет ревью (A6-guardrail 2).
- **OQ-2. Форма ответа `GET /projects/{id}/artifacts`.** **Закрыто (архитектор):** плоский пагинируемый `Page[T]` `{items, total, limit, offset}` с полными путями (`lecture-1/slides.md`); дерево группирует фронт. «list = дерево» брифа читается как семантика UI, не форма ответа; envelope-конвенция сохраняется.
- **OQ-3. Судьба `backend/scripts/seed_demo.py`.** **Закрыто (оркестратор):** вырезать артефактную PG-часть, сидер остаётся полезным для проектов/чатов; «перевести сидинг артефактов на файлы workspace» — кандидат в Follow-ups (harvest).
- **OQ-4 (из PLAN_REVIEW). Хардкод упразднённого инструмента в выжившем тесте.** `backend/tests/agent/test_tool_names_fixture.py:70` ассертит `{"run_subagent", "create_artifact", "generate_image"} <= committed` — файл удалять нельзя, регенерация фикстуры его не чинит. **Закрыто (оркестратор):** трактовка OQ-1 расширяется на этот случай — точечная правка ассерта implementer'ом в T1.5 (снять `create_artifact` из литерала, добавить новые имена по смыслу теста), с фиксацией в `summary.md`; это правка упоминания упразднённого, не эрозия покрытия выжившего.
- **OQ-5 (из PLAN_REVIEW). Фиксация допущения «один uvicorn-воркер».** **Закрыто (оркестратор):** допущение (tool и SSE-подписчик — один процесс, канал эмиссии работает in-process) фиксируется строкой в `summary.md` трека как обязательный пункт для docs-updater (`streaming.md`) — `doc/**` вне скоупа T1, DOC_UPDATE после барьера.
