# Summary: feat-012 / трек T1 — Backend: skill-scoped user context

## TL;DR

Трек T1 завершён целиком (T1.1–T1.5): backend-механизм skill-scoped user context —
Store namespace `("user", uid, "skill_context", skill)`, агентские tools
`get/save/delete_skill_context`, дозагрузка индекса в `load_skill`, новый
security-checkpoint `SKILL_CONTEXT_WRITE`, сервисный слой + Pydantic-схемы, REST CRUD
`/users/me/skill-contexts` (листинг с группировкой/`in_library`, GET/PUT/DELETE item).
Без отступлений от plan.md/design-brief по контракту; одно документированное отклонение
от буквальной формулировки плана в реализации (сигнатура `runtime` в `load_skill` —
см. «Решения и обоснования»). `make check` — зелёный на каждой фазе, финально включая
T1.5. Автотесты (`backend/tests/skill_context/`) — вне скоупа этого плана, пишет
`test-author`.

T1.1 реализована: реестр имён скиллов (`scan_skill_names`) + агентские tools
`get/save/delete_skill_context` над namespace `("user", uid, "skill_context", skill)`.
Без отступлений от plan.md/design-brief. Лимиты (`content` ≤ 20 000, `description` ≤ 200,
≤ 20 документов на скилл при создании нового key) реализованы как error-строки tool'ов, не
исключения — по прецеденту `knowledge_sphere.py`. `save_skill_context` проверяет формат
имени скилла и его наличие в startup-снимке реестра; `get`/`delete` реестр не консультируют
(данные скилла, удалённого из библиотеки, остаются читаемыми/удаляемыми). Оба списка
инструментов (`internal_tools` для security-corpus, `global_tools` для графа) дополнены.
`make check` — зелёный (ruff, mypy, import-linter, arch-checker).

T1.2 реализована: `load_skill` (без `file`) дописывает индекс контекста скилла
(`key: description`) поверх обычного вывода — только когда скилл найден и namespace
непуст; пустой namespace или `file` — выдача не меняется, содержимое документов не
грузится. `make check` и полный backend-тестсьют (`make test`, 648 тестов) — зелёные без
изменений тестовых файлов.

T1.3 реализована: новый security-checkpoint `SKILL_CONTEXT_WRITE` — enum-член,
`Direction.INBOUND`, оба детектора (`canary`/`unicode`) применяются к нему симметрично
`CUSTOM_INSTRUCTIONS_WRITE`/`KS_WRITE_REST`, блок `skill_context_write` в
`configs/security.yaml` (`classifier_enabled: true`). Checkpoint резолвится через
`checkpoint_configs(security_config)` — проверено прямым python-прогоном загрузки
конфига. `make check` — зелёный.

T1.4 реализована: Pydantic-схемы REST (`SkillContextDocument`/`SkillContextGroup`/
`SkillContextListResponse`/`SkillContextUpdate`) и сервис
`LangGraphSkillContextService` (`list_skill_contexts`/`get_document`/
`update_document`/`delete_document`) над Store, с порядком проверок на записи —
404 (существование) → checkpoint `SKILL_CONTEXT_WRITE` → `aput`. Проверено
прямым асинхронным прогоном (не pytest, файл вне скоупа): листинг/группировка/
`in_library`, 404 на всех трёх операциях для отсутствующего документа, guard не
вызывается при 404 (короткое замыкание), блокировка при INJECTION оставляет
данные нетронутыми, security-warning логируется корректными полями, CLEAN-путь
пишет. `make check` — зелёный. T1.5 не начата.

## Реализовано в фазе T1.1

- `backend/app/agent/tools/skills.py` — новая функция `scan_skill_names(skills_dir) ->
  frozenset[str]`: та же логика сканирования директорий со `SKILL.md`, что и у
  `_list_available`, но возвращает множество имён для программных проверок (существование
  скилла в tool'е, флаг `in_library` на REST — фаза T1.5). `_list_available` отрефакторен на
  использование `scan_skill_names` (устранён дублирующийся directory-scan).
- `backend/app/agent/tools/skill_context.py` (новый) — фабрика
  `make_skill_context_tools(skill_names: frozenset[str]) -> list[BaseTool]`, замыкающая
  startup-реестр имён скиллов. Возвращает три tool'а:
  - `get_skill_context(skill_name, key)` — `aget` по namespace `("user", uid,
    "skill_context", skill_name)`; отсутствие документа — error-строка, не исключение.
  - `save_skill_context(skill_name, key, description, content)` — upsert. Проверки в
    порядке: формат имени скилла (`_SKILL_NAME_RE`, импортирован из `skills.py`) →
    существование в реестре → длина `description` (≤ 200) → длина `content` (≤ 20 000) →
    (только если key новый — `aget` вернул `None`) подсчёт документов на скилл через
    `asearch(ns, limit=21)` и отказ при ≥ 20 существующих. Upsert существующего key лимитом
    количества не ограничен.
  - `delete_skill_context(skill_name, key)` — `adelete` по namespace; идемпотентно (нет
    предварительной проверки существования — симметрично `delete_user_memory`).
  Store и `user_id` берутся из `ToolRuntime` (`runtime.store`, `runtime.context.user_id`) —
  приватные хелперы `_store`/`_user_id`/`_ns` по образцу `user_memory.py`/
  `knowledge_sphere.py`. Add-time security-checkpoint в tool не добавлен — аргументы уже
  покрыты runtime-checkpoint `tool_call_arg` (design-brief § Инструменты агента).
- `backend/app/agent/tools/__init__.py` — экспортированы `make_skill_context_tools` и
  `scan_skill_names`.
- `backend/app/main.py` — на старте: `skill_names = scan_skill_names(skills_dir)` →
  `app.state.skill_names` (для REST, фаза T1.5) → `skill_context_tools =
  make_skill_context_tools(skill_names)`. Добавлены в `internal_tools` (для
  security-corpus/fragment-detector) и `global_tools` (для графа) — обе точки регистрации
  рядом с `user_memory_tools`.

**Проверки:** `make check` — зелёный по всему монорепо (ruff lint + format, mypy `backend/`
+ `services/siem-service/` + `tools/*`, import-linter 9/9 контрактов, arch-checker). Прямой
импорт-санити: `make_skill_context_tools(frozenset({"tech-article-writing"}))` создаёт три
tool'а с ожидаемыми именами (`get_skill_context`, `save_skill_context`,
`delete_skill_context`).

## Реализовано в фазе T1.2

- `backend/app/agent/tools/skills.py` — `load_skill` получил третий параметр
  `runtime: ToolRuntime` (инъектируется, невидим для модели). После получения строки от
  `_load_skill_sync` (не тронута): если `file is not None` или результат — строка ошибки
  (`startswith("Error:")`, тот же idiom, что уже использует `test_skills.py`), возвращаем
  как есть. Иначе — новый хелпер `_skill_context_index(runtime, skill_name)` делает
  `asearch(("user", uid, "skill_context", skill_name), limit=20)`; пустой результат → `None`
  (выдача не меняется); непустой → `store_helpers.format_index(items, title="Skill
  Context")` (формат `key: description`, тот же паттерн, что "Knowledge Sphere"/"User
  Memory" в `graph.py`), приклеенный к результату через `\n\n---\n`-разделитель — визуально
  идентичный уже существующему footer'у списка файлов скилла.
  Docstring `load_skill` дополнен упоминанием индекса контекста и `get_skill_context` —
  для обнаружимости моделью.
- `backend/app/main.py` — правок не потребовалось: сигнатура `make_load_skill_tool(skills_dir)`
  не изменилась (только тело инжектируемого tool'а получило параметр), место регистрации
  то же.

**Проверки:** `make check` — зелёный по всему монорепо (то же покрытие, что в T1.1).
`make test` — весь backend-сьют (648 тестов) зелёный, включая 26 существующих тестов
`tests/personalization/test_skills.py`, вызывающих `tool.ainvoke({"skill_name": ...})` без
`runtime` — ни один тестовый файл не редактировался. Ручной прогон (вне pytest) подтвердил
четыре сценария: без runtime, runtime с пустым namespace (оба дают байт-в-байт идентичный
прежнему вывод), runtime с сохранённым документом (индекс дописан, полное содержимое
документа не просочилось в вывод), неизвестный скилл (индекс не дописывается к
error-строке).

## Реализовано в фазе T1.3

- `backend/app/agent/security/types.py` — добавлен `Checkpoint.SKILL_CONTEXT_WRITE =
  "skill_context_write"` и запись `Checkpoint.SKILL_CONTEXT_WRITE: Direction.INBOUND` в
  `_DIRECTION_MAP` — сразу после `KS_WRITE_REST` (порядок объявления зеркалит порядок в
  YAML-конфиге ниже).
- `backend/app/agent/security/detectors/canary.py` и `detectors/unicode.py` —
  `Checkpoint.SKILL_CONTEXT_WRITE` добавлен в `applies_to` обоих детекторов, симметрично
  `CUSTOM_INSTRUCTIONS_WRITE`/`KS_WRITE_REST` (эти два write-checkpoint'а — единственные
  прецеденты персистентной инъекции до этой фазы; skill-context — третий той же природы).
- `configs/security.yaml` — новый блок `skill_context_write` (после `ks_write_rest`,
  перед `messages`): `classifier_enabled: true`, `description` называет точку записи (REST
  API skill-scoped user context) и момент будущей инъекции (surfaced к агенту при
  `load_skill`), `specifics` предписывает оценивать контент так, будто он уже инжектирован
  как доверенный per-user контекст — INJECTION при override/role-switch/раскрытии
  системного промпта или canary, ложной provenance, embedded serialized tool calls;
  легитимная персонализация (voice/style/tone/domain preferences/примеры прежних работ) —
  CLEAN. Текст скомпонован по прецеденту `ks_write_rest` (тот же паттерн
  «evaluate-as-if-already-injected» + explicit INJECTION/CLEAN differentiation), адаптирован
  под skill-context вместо Knowledge Sphere.

**Проверки:** `make check` — зелёный по всему монорепо (ruff lint + format, mypy
`backend/` + `services/siem-service/` + `tools/*`, import-linter 9/9, arch-checker).
Прямой python-прогон подтвердил резолюцию: `checkpoint_configs(load_security_config(...))`
возвращает `CheckpointConfig(classifier_enabled=True, description=..., specifics=...)` для
`Checkpoint.SKILL_CONTEXT_WRITE`; `CanaryDetector.applies_to` и `UnicodeDetector.applies_to`
оба содержат `Checkpoint.SKILL_CONTEXT_WRITE`.

## Реализовано в фазе T1.4

- `backend/app/api/schemas/skill_context.py` (новый) — `SkillContextDocument`
  (`key`, `description`, `content`, `created_at`, `updated_at`, даты
  `datetime` → ISO при сериализации), `SkillContextGroup` (`skill_name`,
  `in_library`, `documents: list[SkillContextDocument]`), `SkillContextListResponse`
  (`{"skills": [...]}`, без конверта пагинации — по design-brief), `SkillContextUpdate`
  (PUT body: `description`/`content` оба обязательны, `Field(max_length=200)` /
  `Field(max_length=20_000)`). Локальные константы `_MAX_DESCRIPTION_LENGTH`/
  `_MAX_CONTENT_LENGTH` в модуле — не импорт из `agent/tools/skill_context.py`
  (см. «Решения»).
- `backend/app/services/skill_context.py` (новый) — dataclasses
  `SkillContextDocumentData`/`SkillContextGroupData`, `Protocol
  SkillContextService`, `LangGraphSkillContextService(store, guard, skill_names)`:
  - `list_skill_contexts(user_id)` — `asearch(("user", uid, "skill_context"),
    limit=500)` (headroom над теоретическим максимумом 20 скиллов × 20
    документов), группировка по `item.namespace[3]` (4-й элемент — имя
    скилла), `in_library` из реестра-снимка (замыкание конструктора, тот же
    `skill_names`, что и у agent tools T1.1), документы внутри группы
    отсортированы по `created_at`, группы — по `skill_name`.
  - `get_document(user_id, skill_name, key)` — `aget`; `None` → `NotFoundError`
    (`f"Skill context '{key}' not found for skill '{skill_name}'"`, → 404 через
    глобальный `AppError`-handler).
  - `update_document(user_id, skill_name, key, *, description, content)` —
    порядок строго по design-brief: `aget` (существование) → `NotFoundError`
    если `None` → guard `Checkpoint.SKILL_CONTEXT_WRITE` (только если
    документ существует — classifier не тратится на заведомо отклоняемый
    404-запрос) → при `Verdict.INJECTION` — `logger.warning` с
    `security_event=True` (поля: `checkpoint`, `verdict`, `identifiers`
    (`user_id`/`skill_name`/`key`), `metadata.detection_layer`) и
    `SecurityPolicyViolationError(reason=...)` (→ 422) → иначе `aput` полной
    заменой value (`{"description", "content"}`) → возврат свежепрочитанного
    документа. Guard-блок структурно идентичен `user_memory.update_instructions`/
    `sphere.update` (trace_ctx: `top_level`, `user_id`, `skill_name`, `key`,
    `scope="skill_context"`).
  - `delete_document(user_id, skill_name, key)` — `aget` (существование) →
    `NotFoundError` если `None`, иначе `adelete`. В отличие от tool'а
    `delete_skill_context` (T1.1, идемпотентен, без предпроверки) — REST-путь
    проверяет существование по прямому предписанию плана/design-brief (404 —
    часть контракта, у tool'а нет HTTP-статусов).

**Проверки:** `make check` — зелёный по всему монорепо (ruff lint + format,
mypy `backend/` + `services/siem-service/` + `tools/*`, import-linter 9/9,
arch-checker). Прямые асинхронные прогоны (вне pytest, `backend/tests/skill_context/`
не создавался — тесты пишет `test-author`) против `InMemoryStore`:
пустая коллекция → `[]`; 404 на `get`/`update`/`delete` для отсутствующего
документа; `FakeGuard` — гвард не вызывается при 404 (короткое замыкание
проверено флагом `guard.called`); `Verdict.INJECTION` → `SecurityPolicyViolationError`
с `reason` из `detection_layer`, документ после блокировки не изменён
(`content` тот же, что до вызова); `Verdict.CLEAN` → запись проходит, повторное
чтение возвращает новые `description`/`content`; листинг группирует два разных
скилла с верными `in_library` (по реестру, переданному в конструктор). Pydantic:
`SkillContextListResponse` сериализуется в форму `{"skills": [...]}` из
design-brief; `SkillContextUpdate` — лимиты 200/20000 и обязательность обоих
полей проверены `ValidationError` на граничных значениях.

## Реализовано в фазе T1.5

- `backend/app/api/routes/skill_context.py` (новый) — `APIRouter` (`tags=["skill-context"]`),
  по прецеденту `user_memory.py`: приватный хелпер `_get_skill_context_service(request)`
  строит `LangGraphSkillContextService` из `request.app.state` (`store`, `security_guard`
  через `getattr(..., None)` — симметрично `_get_memory_service`, и `skill_names` — реестр
  из T1.1). Четыре эндпоинта, аутентификация `CurrentUser`:
  - `GET /users/me/skill-contexts` → `SkillContextListResponse` (группировка + `in_library`
    из сервиса).
  - `GET /users/me/skill-contexts/{skill_name}/{key}` → `SkillContextDocument`; 404 —
    `NotFoundError` из сервиса, маппится глобальным `AppError`-handler.
  - `PUT /users/me/skill-contexts/{skill_name}/{key}` (body `SkillContextUpdate`) →
    `SkillContextDocument`; 404/422 — из сервиса (`NotFoundError`/`SecurityPolicyViolationError`).
  - `DELETE /users/me/skill-contexts/{skill_name}/{key}` → `204`; 404 — из сервиса.
  Ни один route не содержит `try/except` — доменные исключения сервиса маппятся
  глобальным `AppError`-handler (`app/api/problem.py`), как и предписано планом/прецедентом.
- `backend/app/api/routes/__init__.py` — модуль `skill_context` добавлен в импорт и
  `__all__` (по алфавиту, между `settings` и `sphere`).
- `backend/app/main.py` — модуль `skill_context` добавлен в существующий групповой импорт
  из `app.api.routes` (между `projects` и `sphere`, по алфавиту); `app.include_router(
  skill_context.router, prefix=api_prefix)` добавлен рядом с прочими роутерами — сразу
  после `user_memory.router`, перед `mcp_servers.router`.

**Проверки:** `make check` — зелёный по всему монорепо (ruff lint + format, mypy `backend/`
+ `services/siem-service/` + `tools/*`, import-linter 9/9 контрактов, arch-checker). Прямой
импорт-санити: `skill_context.router.routes` даёт ровно четыре маршрута с ожидаемыми
методами/путями (`GET`/`GET`/`PUT`/`DELETE` на `/users/me/skill-contexts` и
`/users/me/skill-contexts/{skill_name}/{key}`) — совпадает с design-brief § REST API
дословно.

Трек T1 завершён (все пять фаз T1.1–T1.5 реализованы); `make check` зелёный на каждом шаге.

## Решения и обоснования

- **`runtime: ToolRuntime = _NO_RUNTIME` (модульный sentinel через `cast`), а не простой
  обязательный параметр.** Это единственная развилка, где план (T1.2: «добавить параметр
  `runtime: ToolRuntime`... как в `user_memory`») разошёлся с фактическим поведением
  фреймворка при попытке реализовать буквально:
  - Обязательный `runtime: ToolRuntime` без default (прецедент `user_memory.py`/
    `skill_context.py`) ломает прямой вызов `tool.ainvoke({"skill_name": ...})` без
    `runtime` — pydantic-валидация полной схемы падает с `ValidationError: Field required`
    ещё до тела функции. Ровно так вызывают `load_skill` все 26 существующих тестов
    `test_skills.py` (файл вне скоупа T1.2, трогать нельзя) — это сломало бы их все.
  - `runtime: ToolRuntime | None = None` — не решение: LangChain-машинерия исключает
    инъектируемый параметр из LLM-facing схемы и required-состояния только когда аннотация
    **точно** `ToolRuntime` (`_is_directly_injected_arg_type` в
    `langchain_core.tools.base`, проверено `inspect`/эмпирически); `Union`/`Optional`
    ломает генерацию JSON Schema (`PydanticInvalidForJsonSchema`, проверено воспроизведением).
  - Рабочий вариант: аннотация остаётся ровно `ToolRuntime` (сохраняет и корректную
    инъекцию в графе — проверено, что `ToolNode` определяет injected-параметры чисто по
    типу аннотации, вне зависимости от наличия default, — и исключение из LLM-схемы), а
    default — `cast("ToolRuntime", None)`, вынесенный в модульную константу `_NO_RUNTIME`
    (не функциональный вызов в сигнатуре — `ruff` B008 запрещает `cast(...)` прямо в
    default; вынос в константу — предложенный самим правилом фикс). Реальное значение при
    вызове без `runtime` — `None`; `_skill_context_index` явно проверяет `runtime is None`
    первым делом.
  - Верифицировано эмпирически (`uv run mypy`, ручные `asyncio`-прогоны) для трёх
    вариантов, прежде чем остановиться на этом; не архитектурная развилка (границ
    контракта/интерфейса T1.2 не меняет), а обход framework-ограничения — эскалация не
    требовалась, но фиксирую здесь как значимое отклонение от буквальной формулировки
    плана.
  - `_NO_RUNTIME` — не нарушает правило «никаких module-level синглтонов»: это
    неизменяемый typed-sentinel (аналог уже существующих `_SKILL_NAME_RE`/
    `_SAFE_PATH_SEGMENT_RE` в этом же модуле), не изменяемое состояние приложения.
- **Обнаружение «скилл найден» через `result.startswith("Error:")`, не отдельная
  проверка файловой системы в async-обёртке.** `_load_skill_sync` уже кодирует «не
  найдено»/«невалидное имя» единственным префиксом `"Error:"` для всех веток (валидировано
  чтением всех `return`); дублировать проверку существования файла в обёртке значило бы
  два места с одной и той же логикой валидации имени/пути, рискующих разойтись. Тот же
  idiom уже используют тесты (`assert content.startswith("Error:")` — 6+ мест в
  `test_skills.py`), так что это не новая договорённость, а следование существующей.
- **Лимит `asearch(..., limit=20)` — локальная константа `_MAX_SKILL_CONTEXT_DOCUMENTS`
  в `skills.py`, не импорт `_MAX_DOCUMENTS_PER_SKILL` из `skill_context.py`.**
  `skill_context.py` уже импортирует `_SKILL_NAME_RE` из `skills.py`; обратный импорт
  создал бы цикл `skills.py → skill_context.py → skills.py`. Число (20) — тот же бизнес-
  инвариант, задокументированный в design-brief и `skill_context.py`; расхождение
  константы отслеживаемо (обе явно закомментированы как отражающие один и тот же лимит).
- **Заголовок индекса — `"Skill Context"` (Title Case).** Совпадает со стилем заголовков
  `format_index` уже в системном сообщении графа (`"Knowledge Sphere"`, `"User Memory"` в
  `graph.py`), хотя `load_skill`-индекс инжектится не в system message, а в tool-ответ —
  сохранена визуальная консистентность формата индекса по всему проекту.
- **Импорт `_SKILL_NAME_RE` напрямую из `skills.py` (приватное имя через границу модуля).**
  План буквально указывает переиспользовать этот регекс («по `_SKILL_NAME_RE`») —
  единственный источник правды для формата имени скилла, используемый и в `load_skill`
  (`_load_skill_sync`), и теперь в `save_skill_context`. Дублирование константы создало бы
  риск рассинхронизации; ruff/mypy такой cross-module импорт приватного имени не
  флагуют (в проекте нет правила вроде pylint `protected-access` в `[lint.select]`).
  Публичное переименование не сделано — не входило в план, а расширение публичного API
  модуля `skills.py` сверх заявленного — не в скоупе фазы.
- **Лимит документов проверяется через `asearch(ns, limit=_MAX_DOCUMENTS_PER_SKILL + 1)`
  (21), не `limit=20`.** Нужно отличить «ровно 20 существующих» (при котором создание 21-го
  должно быть отклонено) от `limit=20`, который срезал бы выдачу на 20 и дал тот же `len()`
  независимо от того, 20 их или больше — `limit=21` даёт точный подсчёт до порога включительно
  без риска смешать «обрезано лимитом» с «фактически столько и есть».
- **`delete_skill_context` не проверяет существование документа перед `adelete`.**
  Design-brief задаёт эту проверку для REST-пути (`delete_document` в T1.4, где 404 —
  часть контракта). У tool'а нет HTTP-статусов — по прецеденту `delete_user_memory` (`aget`
  перед `adelete` отсутствует) delete tool идемпотентен: повторный вызов с тем же
  `(skill_name, key)` не создаёт разной наблюдаемой ошибки для агента. `get_section`/
  `delete_section` в `knowledge_sphere.py` — исключение из этого прецедента (проверяют и
  возвращают error-строку), но `user_memory.py` — более точный образец для skill-context
  (design-brief явно ссылается на `user_memory.py`/`store_helpers.py` как прецеденты, не на
  `knowledge_sphere.py`).
- **`scan_skill_names` вынесена в `skills.py`, не в новый `skill_context.py`.** План явно
  относит её к `skills.py` («добавить startup-хелпер... по логике `_list_available`») —
  единый источник «библиотеки» живёт рядом с существующей логикой сканирования скиллов
  (`scan_skills_index`, `_list_available`), а не в модуле, специфичном для
  skill-context-tools. `skill_context.py` только потребляет реестр как параметр фабрики,
  не строит его.
- **`app.state.skill_names` заведён в T1.1, хотя потребитель (REST `in_library`) — только
  в T1.5.** План явно предписывает это для фазы T1.1 («собрать реестр имён на старте,
  положить в `app.state` (для REST)») — реестр строится один раз в единственном месте
  старта приложения рядом с конструированием skill-context tools, использующих тот же
  `skill_names`; заведение `app.state`-поля заранее не создаёт риска для T1.2–T1.5 (поле
  просто не читается до REST-фазы).
- **Лимиты (200/20 000) в `api/schemas/skill_context.py` — локальные константы,
  не импорт `_MAX_DESCRIPTION_LENGTH`/`_MAX_CONTENT_LENGTH` из
  `agent/tools/skill_context.py`.** Design-brief прямо предписывает независимую
  валидацию («Валидация симметрична: Pydantic на REST, проверки в tools») — два
  раздельных enforcement-пути одного бизнес-инварианта, не единый источник с
  общим импортом. Импорт создал бы также нежелательную связность слоёв:
  `api/schemas` (REST-контракт) не должен знать о существовании конкретного
  agent-tool модуля, реализующего тот же лимит. Тот же паттерн (сознательное
  дублирование константы с комментарием, а не cross-module импорт) уже выбран
  в T1.1 для `_MAX_SKILL_CONTEXT_DOCUMENTS`/`_MAX_DOCUMENTS_PER_SKILL` — здесь
  расширен на пару REST/tool, а не только tool/tool.
- **`update_document`/`delete_document` делают отдельный `aget` перед
  действием, хотя `update_document` уже мог бы переиспользовать результат
  первого `aget` вместо повторного чтения после `aput`.** После `aput` вызван
  `get_document` заново (а не собран `SkillContextDocumentData` вручную из
  входных `description`/`content` + `existing.created_at`), чтобы
  `updated_at`/`created_at` в ответе были ровно тем, что реально записал Store
  (единственный источник истины для таймстемпов), а не предположением о его
  поведении на клиенте сервиса — на один лишний `aget` дороже, но исключает
  расхождение, если у backend Store окажется иная семантика `updated_at` при
  `aput` (например, отложенная запись/кеш).

## Follow-ups

## SOFA-посты (id / применил / результат)
