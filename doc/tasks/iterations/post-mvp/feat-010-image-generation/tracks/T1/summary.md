# Summary: трек T1 — Backend + Agent

## T1.1: Модель `artifact_blobs` + миграция

**Реализовано:**
- `backend/app/models/artifact_blob.py` (новый) — модель `ArtifactBlob`: собственный
  UUID PK (`id`), FK `artifact_id → artifacts.id` (`ondelete="CASCADE"`, `unique=True`,
  `index=True` — 1:1 к артефакту), `mime_type: Text`, `data: LargeBinary` (→ `bytea`).
  Relationship `artifact` (back_populates) к `Artifact`.
- `backend/app/models/artifact.py` — добавлен опциональный relationship
  `blob: Mapped[ArtifactBlob | None]` (back_populates, default lazy-стратегия `select` —
  не подгружается eager при обычном select артефактов/листинге).
- `backend/app/models/__init__.py` — импорт `ArtifactBlob` + запись в `__all__` (нужно
  для autogenerate через `target_metadata = Base.metadata` в `alembic/env.py`).
- Миграция `backend/alembic/versions/05b404b12f90_add_artifact_blobs_table.py` —
  autogenerate против запущенной БД (`make migration msg="add artifact_blobs table"`).
  Проверено по файлу и по фактической DDL (`\d artifact_blobs`): `data bytea NOT NULL`,
  FK `fk_artifact_blobs_artifact_id_artifacts` с `ON DELETE CASCADE`, единственный
  unique-индекс `ix_artifact_blobs_artifact_id`, PK `pk_artifact_blobs` — все имена по
  naming convention. Цикл `upgrade → downgrade -1 → upgrade` без ошибок; на чистой БД
  (`docker compose down -v` → `make docker-up-db` → `make migrate`) вся цепочка миграций
  до head применяется без ошибок.

## T1.2: `BlobStorage` protocol + `PgBlobStorage`

**Реализовано:**
- `backend/app/repositories/blob_storage.py` (новый) — `BlobStorage` (`typing.Protocol`):
  `put(*, artifact_id, data, mime_type) -> None`, `get(artifact_id) -> tuple[bytes, str] |
  None`, `delete(artifact_id) -> None`. Сигнатуры без параметра `session` — по решению
  design-brief (`PgBlobStorage` — единственная реализация, session связывается в
  конструкторе, как у `ArtifactRepository`).
- `PgBlobStorage(session)` — единственная реализация: `put` создаёт `ArtifactBlob` и
  флашит; `get` — `select(ArtifactBlob.data, ArtifactBlob.mime_type).where(artifact_id ==
  ...)`, возвращает `None` при отсутствии строки; `delete` — `delete(ArtifactBlob).where
  (artifact_id == ...)` + flush.
- Соответствие `PgBlobStorage` протоколу `BlobStorage` подтверждено структурно через
  mypy (явного наследования от `Protocol` нет — по паттерну `SphereService` /
  `DeterministicDetector` в кодовой базе).

## T1.3: Media endpoint

**Реализовано:**
- `backend/app/api/routes/artifacts.py` — `GET
  /projects/{project_id}/artifacts/{artifact_id}/media`. Паттерн 1:1 с `get_artifact`:
  `service.get_artifact(artifact_id)` (404 через `EntityNotFoundError` → problem+json,
  если артефакта нет вовсе) + ручная проверка `artifact.project_id != project.id` → 404
  (чужой проект). Затем `blob_storage.get(artifact_id)`; `None` → 404 (`"Artifact media
  not found"`). Успех — `Response(content=data, media_type=mime_type, headers={"Cache-
  Control": "private, max-age=31536000, immutable"})`.
- `backend/app/api/deps.py` — `get_blob_storage(session: DBSession) -> BlobStorage:
  return PgBlobStorage(session)` + `BlobStorageDep = Annotated[BlobStorage,
  Depends(get_blob_storage)]`. Импорт `BlobStorage`/`PgBlobStorage` — напрямую из
  `app.repositories.blob_storage` (без прогона через `app/repositories/__init__.py`
  `__all__`) — по прецеденту `MCPServerRepository`, которая в `deps.py` тоже
  импортируется из своего модуля напрямую, не из пакетного `__init__`.

## T1.4: Конфиг `image` + вызов OpenRouter Image API

**Реализовано:**
- `configs/agent.yaml` — секция `image`: `model: google/gemini-3.1-flash-image`,
  `params: {}`.
- `backend/app/agent/config.py` — `ImageConfig(BaseModel)` (`model: str`,
  `params: dict[str, Any] = {}`) + поле `image: ImageConfig` в `AgentConfig` —
  обязательное, без дефолта (fail-fast по решению архитектора, Open Question #2 в
  плане). `load_agent_config()` роняется с `ValidationError`, если секция отсутствует
  в YAML.
- `backend/app/config.py` — `llm_image_timeout_seconds: int = 120` в блоке
  «Operational knobs» рядом с остальными LLM-таймаутами. `.env.example` синхронно
  дополнен строкой `LLM_IMAGE_TIMEOUT_SECONDS=120`. `.env.local.example` и
  `docker-compose.yml` **не тронуты осознанно** — см. «Решения и обоснования».
- `backend/app/infra/image_generation.py` (новый) — `generate_image(settings,
  image_config, *, prompt, aspect_ratio=None, resolution=None) ->
  ImageGenerationResult` (`@dataclass(frozen=True)`: `data: bytes`, `media_type: str`,
  `cost: float | None`). `httpx.AsyncClient` POST на `{settings.llm_base_url}/images`,
  `Authorization: Bearer {settings.llm_api_key}`, тело `{"model", "prompt",
  ["aspect_ratio"], ["resolution"], **image_config.params}` (последний ключ
  переопределяет предыдущие при коллизии — `params` идёт после позиционных полей,
  «operator-конфиг важнее агентского аргумента» не требовался явно, но порядок
  зафиксирован для предсказуемости). Ответ парсится по подтверждённой офиц. доке
  OpenRouter (см. «Решения и обоснования» — live-fetch): `data[0].b64_json` +
  `data[0].media_type` (оба поля внутри элемента `data[0]`, не на верхнем уровне
  ответа) → `base64.b64decode(..., validate=True)`, `usage.cost` (может быть `None`,
  если провайдер его не вернул). Non-2xx → `UpstreamUnavailableError` `502
  image-generation-failed` (соответствует биллингу all-or-nothing OpenRouter: неуспех
  = не тарифицируется, возвращает 502 по их же доке); сетевая ошибка/таймаут → `503
  image-generation-unavailable`; невалидный/усечённый JSON или отсутствующие
  `data[0].b64_json`/`media_type` → `502 image-generation-malformed-response`;
  невалидный base64 → тот же код. Ни в одном из путей ошибки функция не производит
  побочных эффектов (нет частичной записи — она и не открывает транзакцию, это
  забота T1.5).

**Проверки:**
- `make check` — зелёный (ruff, mypy по всем пакетам, import-linter contracts,
  arch-checker) после фикса двух existing-тестов (см. «Решения»).
- Импорт-санити: `load_agent_config()` из обновлённого `agent.yaml` резолвит секцию
  `image` без ошибок; `from app.infra.image_generation import generate_image` не
  вызывает циклического импорта ни в порядке `app.infra.image_generation` первым, ни
  после `import app.agent` (форсирует цепочку `app.agent.__init__` → `runner` →
  `infra.llm`).
- Функция прогнана офлайн через `httpx.MockTransport` (не через сеть — см. «живой
  вызов» ниже) на 6 сценариях: успех (декод bytes + `media_type` + `cost`), upstream
  400, upstream 502, timeout, пустой `data`, невалидный base64 — все ветки вернули
  ожидаемый `UpstreamUnavailableError.status`/`.code`.
- **Живой вызов OpenRouter — отложен до TEST-фазы.** В `.env` `LLM_API_KEY` стоит на
  плейсхолдере (`your-api-key-here`), в `.env.local` переменная не задана вовсе —
  реального ключа в окружении нет. Вместо живого вызова формат ответа сверен по
  официальной доке OpenRouter (см. «Решения и обоснования») — совпадает с
  design-brief дословно (`data[0].b64_json` + `data[0].media_type`, `usage.cost`,
  502 на неуспешную/отменённую генерацию).

## T1.5: Tool `generate_image` + wiring + расширение маппера SSE

**Реализовано:**
- `backend/app/agent/tools/image_generation.py` (новый) — `make_generate_image_tool
  (session_factory, settings, image_config, *, langfuse_enabled=False)` по паттерну
  `make_create_artifact_tool`: замыкание над зависимостями, `@tool(response_format=
  "content_and_artifact")`. Сигнатура tool'а — `generate_image(prompt, title,
  aspect_ratio=None, resolution=None, *, runtime: ToolRuntime)` (keyword-only `runtime`
  после параметров с дефолтами — паттерн `update_section` в `knowledge_sphere.py`, не
  `create_artifact`, у которого дефолтных параметров не было). Docstring — промптинг-блок
  из design-brief § «Промптинг и выбор параметров», переписан на английский под формат
  docstring (Args-секция + инлайновые правила) — по прецеденту всех остальных
  tool-docstring'ов и `system.txt` (агентские инструкции в проекте на английском,
  независимо от языка внутренней документации).
  Тело: вызов `app.infra.image_generation.generate_image` (T1.4) вне транзакции → при
  успехе одна транзакция (`async with session_factory() as session, session.begin()`) —
  `ArtifactRepository(session).create(type="image", content=prompt, ...)` +
  `PgBlobStorage(session).put(artifact_id=..., data=result.data, mime_type=
  result.media_type)` → (если `langfuse_enabled`) generation-observation
  (`get_client().start_as_current_observation(as_type="generation", name=
  "generate-image", model=image_config.model, input=prompt, output={...},
  cost_details={"total": result.cost})`, весь блок под `contextlib.suppress(Exception)` —
  паттерн `observer.py`; `cost_details` не передаётся, если `usage.cost` пришёл `None`, —
  не подставляем фиктивный 0). ToolMessage-текст: title, id, resolution (или "provider
  default", если агент не передал), cost (или "unknown"); второй элемент tuple — dict
  `{"id", "title", "type": "image"}` для `artifact_created`.
  Ошибка провайдера: `generate_image`-хелпер (T1.4) поднимает `UpstreamUnavailableError`
  **до** открытия `session.begin()` — транзакция физически не начинается, частичной
  записи не может быть. Само исключение из tool'а наружу не ловится — по конвенции
  `conventions.md § Агентные tools`: `ToolNode(tools, handle_tool_errors=_handle_tool_error)`
  в `graph.py` — единая точка перехвата, которая логирует `exc_info` и кладёт безопасный
  текст в `ToolMessage(status="error")`; повторный try/except внутри tool'а был бы
  дублирующим барьером.
- `backend/app/agent/tools/__init__.py` — экспорт `make_generate_image_tool` (импорт +
  `__all__`).
- `backend/app/main.py` — `generate_image = make_generate_image_tool(app.state.
  session_factory, settings, agent_config.image, langfuse_enabled=langfuse_enabled)`
  сконструирован сразу после `create_artifact` (тот же `session_factory`, `settings` и
  `langfuse_enabled` уже в скоупе на этой строке — переиспользованы, не заведены заново).
  Добавлен в `internal_tools` и `global_tools` рядом с `create_artifact`.
- `backend/app/agent/stream_events.py` — условие эмита `artifact_created` расширено:
  `msg.name == "create_artifact"` → `msg.name in {"create_artifact", "generate_image"}`
  (плюс существующая проверка `msg.artifact is not None`). Форма события и поля не
  менялись.

**Проверки:**
- `make check` — зелёный по всему монорепо: ruff (lint + format), mypy (`backend/`,
  `services/siem-service/`, `tools/security-scan` + `tools/arch-checker`),
  import-linter (9/9 контрактов kept), `arch-checker` (все AST-проверки прошли).
- `ruff format` потребовал перезаписи `backend/app/main.py` после точечных правок
  (перенос многострочных списков `internal_tools`/`global_tools`) — применено
  автоформаттером, содержательных изменений не внесло.

## Решения и обоснования

- **DI: отдельная `BlobStorageDep` поверх `DBSession`, не метод `ArtifactService`.**
  План допускал оба варианта («по месту, консистентно с существующим DI»). Выбрана
  отдельная зависимость по аналогии с `get_artifact_service`/`ArtifactServiceDep`, а не
  расширение `ArtifactService` методом доступа к блобу: `ArtifactService` инкапсулирует
  бизнес-логику над `Artifact` (get/list), а доступ к байтам блоба — отдельная забота
  без общей бизнес-логики с сервисом артефактов (в `PgBlobStorage` уже нет ORM-объекта
  `Artifact`, только `(bytes, mime_type)`). Раздельные DI-объекты держат `ArtifactService`
  сфокусированным и не заставляют его знать о `BlobStorage` только ради одного
  read-only метода. Хендлер компонует оба через `Depends`, как обычный REST-паттерн
  «несколько зависимостей — один handler» (пагинация + сервис в `list_artifacts` —
  аналогичный пример в том же файле).
- **404 «нет артефакта» vs «нет проекта» vs «нет блоба» — три разные причины, один
  статус-код.** Все три ветки отдают `404`, но не консолидированы в общий guard-clause:
  первая (артефакт не существует) идёт через доменное исключение `EntityNotFoundError`
  из `ArtifactService.get_artifact` (унаследовано от `get_artifact` — не переизобретаем),
  вторая (чужой проект) и третья (блоб не залит) — прямой `HTTPException` в хендлере, по
  паттерну существующих `get_artifact`/`download_artifact` в этом же файле. Разные
  `detail`-сообщения («Artifact not found» vs «Artifact media not found») — не влияют на
  контракт (тело problem+json клиент T2 не парсит по `detail`, ориентируется на
  `status`), но диагностически различимы в логах/девтулзах.
- **Заголовок `Cache-Control` — литеральная строка в `headers=`, не helper.** У
  `download_artifact` в этом же файле уже есть локальный helper `_content_disposition`
  для генерации заголовка, но там he-header параметризован (`filename`), а
  `Cache-Control` на media endpoint — константа из design-brief без вариаций
  (иммутабельность по построению: новый артефакт = новый `id` = новый URL). Отдельная
  функция/константа ради одной строки, используемой в одном месте, — не оправдана.

- **Отдельный PK вместо FK-как-PK.** В кодовой базе есть прецедент 1:1-таблиц через
  FK-как-PK без отдельного surrogate key (`UserSettings`/`ProjectSettings`/
  `ThreadSettings` — `user_id`/`project_id`/`thread_id` как `primary_key=True`
  напрямую на FK). Для `ArtifactBlob` фаза плана явно предписывает другую форму: «PK,
  FK artifact_id ... unique для 1:1» — то есть собственный `id` плюс `artifact_id` как
  unique-FK, не FK-как-PK. Реализовано строго по формулировке плана, а не по ближайшему
  прецеденту в коде: design-brief прямо называет таблицу будущим общим хранилищем под
  file attachments и референсные изображения (backlog), где natural key — не
  единственный на потребителя блоба, а собственный `id` держит эту дверь открытой без
  будущей миграции PK.
- **`unique=True` + `index=True` на одной колонке.** `unique=True` в SQLAlchemy 2.0 сам
  по себе не гарантирует физический индекс с предсказуемым именем (может лечь как
  `UniqueConstraint`), а `index=True` — гарантия, что constraint пойдёт по
  `ix_`-конвенции из `models/base.py` (`NAMING_CONVENTION`). Комбинация даёт один
  unique-индекс на `artifact_id`, не два физических объекта — подтверждено
  сгенерированной миграцией (один `op.create_index(..., unique=True)`, отдельного
  `UniqueConstraint` нет) и фактической DDL в Postgres.
- **`LargeBinary` вместо `BYTEA` напрямую.** `LargeBinary` — диалект-независимый тип
  SQLAlchemy, который на Postgres транслируется в `bytea`; используется вместо
  `sqlalchemy.dialects.postgresql.BYTEA`, чтобы не завязывать модель на
  postgres-диалект без необходимости (весь остальной проект тоже не тянет
  postgres-специфичные типы, кроме `JSONB`, где это осознанный выбор в `settings.py`).
- **Relationship без явного `lazy=`.** Default lazy-стратегия SQLAlchemy для
  `relationship()` — `"select"` (ленивая, отдельным запросом при обращении), не eager
  join. Она уже удовлетворяет требованию плана «не тянуть блоб в дефолтный select
  (listing артефактов не должен грузить мегабайты)» без дополнительной настройки —
  явный `lazy="select"` не добавлен как избыточный (default и так `"select"`).
- **`get` без промежуточного `session.get(ArtifactBlob, ...)` + отдельного select по
  `artifact_id`.** PK блоба — собственный `id`, а протокол адресует блоб по
  `artifact_id` (естественный ключ доступа для media endpoint и tool'а — они знают
  `artifact_id`, не `blob.id`). Прямой `select(ArtifactBlob.data,
  ArtifactBlob.mime_type).where(artifact_id == ...)` возвращает только нужные две
  колонки одним запросом, без загрузки полноценного ORM-объекта `ArtifactBlob` — не
  тянет лишние атрибуты ради двух полей.
- **`delete` — bulk `delete()` + flush, а не `session.get` + `session.delete`.**
  `PgBlobStorage.delete` работает по `artifact_id` (не по загруженному объекту), поэтому
  bulk-DML `sqlalchemy.delete(ArtifactBlob).where(...)` избегает лишнего
  round-trip'а на предварительную загрузку строки — согласуется с тем, что вызывающая
  сторона (будущий tool/сервис) не обязана держать ORM-инстанс блоба для удаления.

- **Хелпер вызова OpenRouter — `backend/app/infra/image_generation.py`, не в модуле
  tool'а.** План допускал оба места. Выбран `infra/` по прямой аналогии с
  `infra/llm.py`: это тонкая обёртка над внешним HTTP API провайдера, без знания о
  tool-контракте LangChain (`response_format`, `ToolMessage`, транзакции) — та же
  граница ответственности, что у `create_llm_from_config`/`create_summarization_llm`.
  Помещение в `agent/tools/image_generation.py` (T1.5) смешало бы «вызвать
  провайдера» с «собрать tool», тогда как T1.4 и T1.5 — разные фазы с разной
  ответственностью; текущее разделение позволяет T1.5 тестировать сборку tool'а с
  замоканным `generate_image`, не трогая httpx-логику.
- **`ImageConfig` импортируется в `infra/image_generation.py` только под
  `TYPE_CHECKING`, `Settings` — напрямую.** Тот же паттерн, что в `infra/llm.py`
  (комментарий в коде цитирует то же обоснование): импорт `app.agent.config` на
  уровне модуля форсирует инициализацию `app.agent/__init__.py` →
  `app.agent.runner`, а эта цепочка утягивает `app.infra.llm` (и в перспективе — этот
  же `infra.image_generation` из будущего `agent/tools/image_generation.py`,
  T1.5) — потенциальный цикл при импорте `app.infra.image_generation` раньше
  `app.agent`. `Settings` — лист зависимостей (как в `infra/db.py`/`infra/redis.py`),
  риска нет, импортируется обычным образом. Проверено рантайм-импортом в обоих
  порядках (`app.infra.image_generation` первым и после `import app.agent`) — цикла
  нет ни в теории (структура импортов), ни на практике.
- **`media_type` читается из `data[0].media_type`, не с верхнего уровня ответа.**
  Design-brief и текст фазы плана формулируют это как «`data[0].b64_json` +
  `media_type`», что можно прочитать двояко (поле на верхнем уровне или внутри
  элемента `data[0]`). Официальная дока OpenRouter
  (`openrouter.ai/docs/guides/overview/multimodal/image-generation`, раздел Response
  Format) даёт точный пример ответа: `{"data": [{"b64_json": "...", "media_type":
  "image/png"}], "usage": {...}}` — оба поля внутри элемента массива `data`, не
  соседи на верхнем уровне. Реализовано по доке, не по буквальному прочтению плана;
  разночтения с design-brief нет по существу (там тот же порядок слов, тот же смысл).
- **`UpstreamUnavailableError` на трёх разных кодах ошибок, не один общий.**
  `image-generation-failed` (502, non-2xx от провайдера — совпадает с задокументированным
  у OpenRouter поведением: неуспешная/отменённая генерация не тарифицируется и
  возвращает 502), `image-generation-unavailable` (503, сетевая ошибка/таймаут —
  зависимость недоступна, а не отказала осмысленно) и
  `image-generation-malformed-response` (502, ответ 2xx, но без ожидаемых полей —
  контракт с провайдером нарушен на его стороне). Разные `code` дают разные логи и
  разную диагностику, не просто разный `detail`; статусы обоих «на стороне
  провайдера» кодов — 502, потому что оба говорят «удалённая сторона ответила, но
  не тем, что нужно», в отличие от 503 (сторона не ответила вовсе).
- **Live-вызов подтверждён по официальной доке, а не только по design-brief.**
  Design-brief прямо предупреждает: «в доках Google таблицы токенов расходятся —
  канон прайс-страница, фактический расход сверить по `usage` живым вызовом при
  реализации» — то есть заранее закладывает, что схема ответа нуждается в проверке.
  Реального `LLM_API_KEY` в окружении не оказалось (см. секцию T1.4 выше), поэтому
  вместо живого вызова офиц. дока OpenRouter (не Google — сам shape ответа
  Image API, не токеномика конкретной модели) была прочитана явно и сверена
  построчно с реализацией парсинга; полная проверка фактического `usage.cost` для
  `google/gemini-3.1-flash-image` (расхождение таблиц у Google) остаётся за
  TEST-фазой, где ожидается реальный ключ.
- **`.env.local.example` и `docker-compose.yml` не тронуты, несмотря на «atomic
  change по четырём местам» из conventions.md.** Проверено по факту: `app`-сервис в
  `docker-compose.yml` подключает переменные целиком через `env_file: [.env]`, без
  явного перечисления в `environment:` (в отличие от `siem-service`, который их
  перечисляет построчно — там `env_file` не используется). Ни один из существующих
  LLM-таймаутов (`LLM_GUARD_TIMEOUT_SECONDS`, `LLM_SUMMARIZER_TIMEOUT_SECONDS`,
  `LLM_MAX_RETRIES`) не встречается в `docker-compose.yml` — новый
  `LLM_IMAGE_TIMEOUT_SECONDS` следует тому же паттерну, добавлять нечего.
  `.env.local.example` содержит только **отличия** от `.env` для local dev (у него
  такая роль по conventions.md § Docker); ни один из существующих LLM-таймаутов там
  тоже не переопределяется — значение 120 одинаково для docker/local dev. Синхронизация
  реально задета в одном месте: `.env.example` (шаблон полного `.env`) + `Settings`.
- **Два существующих теста (`tests/personalization/conftest.py`,
  `tests/personalization/test_model_config_resolver.py`) дополнены
  `image=ImageConfig(...)`.** Не входят в скоуп T1.4 по содержанию (personalization,
  не image-generation), но `mypy` ловил их как `call-arg` сразу после того, как поле
  `image` стало обязательным в `AgentConfig` — прямое и ожидаемое следствие Open
  Question #2 (fail-fast, решение архитектора), не случайная находка дрейфа. Правка
  чисто механическая: добавлен один аргумент в существующие фабрики `AgentConfig(...)`,
  логика тестов не менялась. Без этой правки `make check` не проходит по причине,
  прямо вызванной этой фазой, — не эскалация «падает не из-за моей задачи».

- **`runtime: ToolRuntime` — keyword-only (`*, runtime: ...`), не последний позиционный
  как в `create_artifact`.** У `generate_image` есть параметры с дефолтами
  (`aspect_ratio`/`resolution`), а Python не позволяет позиционный параметр без дефолта
  после параметров с дефолтом. `create_artifact` этой проблемы не имел (все параметры
  обязательные). В кодовой базе уже есть прецедент ровно этой комбинации —
  `update_section` в `knowledge_sphere.py` (`target: str = "", description: str = "",
  *, runtime: ToolRuntime`) — сигнатура `generate_image` следует этому прецеденту, а не
  изобретает новый. Порядок инъекции `ToolRuntime` не зависит от позиции (langgraph
  различает injected-параметры по типу аннотации при сборке tool-схемы для LLM, не по
  месту в сигнатуре) — `*`-барьер нужен только для валидности Python-сигнатуры.
- **`cost_details` не передаётся в Langfuse-observation, если `usage.cost is None`.**
  OpenRouter не гарантирует поле `cost` в `usage` (T1.4: тип `float | None`). Подстановка
  `{"total": 0}` на его месте создала бы ложный сигнал «генерация бесплатна» в Langfuse
  cost-отчётах — хуже, чем отсутствие `cost_details` у конкретной observation (заметно
  как пробел в данных, не как неверная цифра).

## Follow-ups

(пусто)

## SOFA-посты (id / применил / результат)

(пусто)
