# Test Cases: feat-012 — Skill-scoped user context / трек T1 (backend)

Трек T1 даёт бэкенд-механизм per-user контекста, привязанного к скиллу: четвёртый namespace
Store `("user", uid, "skill_context", <skill>)`, агентские tools `get/save/delete_skill_context`,
дозагрузку индекса документов при `load_skill`, новый security-checkpoint `SKILL_CONTEXT_WRITE` и
REST CRUD `/users/me/skill-contexts`. Это новая фича (не поведение-сохраняющий рефактор), поэтому
кейсы подтверждают заявленный контракт design-brief, а не совместимость со старым поведением.

Кейсы страхуют пять свойств контракта: изоляцию документов по `user_id`+`skill_name` сквозь tools и
REST; двухуровневый progressive disclosure (`load_skill` дописывает только индекс `key: description`,
содержимое тянется отдельным tool'ом); бизнес-лимиты (`content` ≤ 20 000, `description` ≤ 200,
≤ 20 документов на скилл при создании нового key) одинаково в tools и на REST; порядок проверок на
записи (404 существования раньше security-checkpoint — guard не тратится на заведомо отклонённый
запрос) и блокировку персистентной инъекции при вердикте INJECTION; развязку хранения и наличия
скилла в библиотеке (данные переживают удаление скилла — `in_library=false`, но документы читаемы).

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры**: `📊` — проверка наблюдаемости (структура БД/Store, метрики, Langfuse); `🔴` — проверка реальных инъекций / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `tests/skill_context/`); `*(регресс)*` — кейс страхует «поведение не сломалось».
- **run-log** (только у перепрогнанных кейсов): `runs: r1 ✅ → r2 ❌ (причина) → r3 ✅`.

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`/`make test`) — перепрогон всегда; ручные кейсы — перепрогон затронутой области. Каждый перепрогон → запись в run-log.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики: не сошлось — повтори (транзиент); не сошлось второй раз — fail + эскалация. Инструменты: structlog (JSON stdout), Langfuse traces, состояние Store, БД. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer**, не сам тестировщик.

**Скоуп по трекам.** Кейсы с префиксом трека (`{T1.x}`) гоняются на своём треке + Layer 0; cross-cutting (Layer 2/3 без префикса) — в INTEGRATION_TEST. Не пропускать кейсы молча — неприменимый помечать причиной.

### Процесс (тестировщик поднимает стенд сам)

1. Инфраструктура: `make docker-up-db` (Postgres), `make migrate`, backend `make dev`, фронт `make dev-fe` (для Layer 2/3) — либо `make docker-up` целиком.
2. Акторы через UI register / `/api/auth/register`: **user-a** и **user-b** (обычные пользователи — для проверки per-user изоляции). Понадобится хотя бы один реальный скилл в библиотеке (например `tech-article-writing`) и один документ, сохранённый агентом.
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в run-log + `## Решения и обоснования` summary трека.
4. После прогона — сводка (pass / failed / **deferred**). Deferred — кейсы 👤/заблокированные: отдельным счётчиком + причина.

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| Store (skill_context) | REST `GET /api/users/me/skill-contexts` или прямой запрос к таблице Store |
| Сеть / SSE | DevTools → Network |
| Security-события | structlog stdout (`security_event=True`), Langfuse traces |

---

## Дизайн автотестов

Все автотесты трека живут в `backend/tests/skill_context/` (новая директория скоупа). Общие фейки
берутся из `packages/testing`: `StubGuard` (детерминированный guard с фиксированным вердиктом,
записывает вызовы в `.calls`) — используется в service- и route-тестах. Реальный LLM в CI не
вызывается: guard-путь проверяется на подставленном вердикте, а не на качестве классификации.
Fake-раннера/модели агента здесь нет — весь скоуп детерминирован фейковым guard и реальным
`InMemoryStore` (ин-процесс сосед, не подменяется). REST-слой поднимает реальный Postgres только под
аутентификацией (фикстура `current_user`), сам skill-context живёт в `InMemoryStore` на `app.state`.

**Покрываем автотестом:**

### `test_skill_context_tools.py` — агентские tools get/save/delete_skill_context

1. **Файл**: `backend/tests/skill_context/test_skill_context_tools.py` — sociable-unit, реальный `InMemoryStore` + duck-typed `ToolRuntime` (`SimpleNamespace(store, context)`), прямой вызов `tool.coroutine(...)`.
2. **Тестирует**: `app.agent.tools.skill_context :: make_skill_context_tools` (`get_skill_context`, `save_skill_context`, `delete_skill_context`).
3. **Суть**: Гарантирует, что `save` кладёт документ под namespace `("user", uid, "skill_context", skill)` со значением `{description, content}`, изолирует документы по имени скилла и по пользователю, а upsert перезаписывает существующий key. Проверяет, что `save` отклоняет запись под неизвестный или синтаксически невалидный скилл (осиротевшие namespace не создаются) и применяет все три бизнес-лимита, включая тонкость «≤ 20 документов проверяется только при создании нового key, upsert на пределе разрешён». Подтверждает, что `get` возвращает полное содержимое и читает документ даже для скилла, отсутствующего в библиотеке (данные переживают скилл), а `delete` удаляет и остаётся идемпотентным на отсутствующем документе. Ловит fail-fast, когда в runtime нет store или context.
4. **Кейсы**:
   - save: персист под skill-namespace со значением `{description, content}`
   - save: upsert перезаписывает значение существующего key
   - save: изоляция по `skill_name` (один key под двумя скиллами не сталкивается)
   - save: изоляция по `user_id`
   - save: отказ на неизвестный скилл (`not found in library`), namespace не создан
   - save: отказ на невалидный формат имени (parametrize: пробел, upper, слэш, `..`, точка)
   - save: отказ при `description` > 200
   - save: отказ при `content` > 20 000
   - save: граница — `content` ровно 20 000 принимается
   - save: 21-й новый key при 20 существующих отклонён (`limit reached`)
   - save: upsert существующего key на пределе 20 документов разрешён
   - get: возврат полного содержимого
   - get: отсутствующий документ → error-строка
   - get: чтение документа скилла, отсутствующего в библиотеке
   - delete: удаление документа
   - delete: идемпотентность на отсутствующем документе
   - fail-fast: нет store → RuntimeError; нет context → RuntimeError

### `test_load_skill_context_index.py` — дозагрузка индекса в load_skill

1. **Файл**: `backend/tests/skill_context/test_load_skill_context_index.py` — sociable-unit, throwaway skills-дерево под `tmp_path` + реальный `InMemoryStore` + duck-typed `ToolRuntime`, вызов `tool.coroutine(...)` (инъекция runtime) и `tool.ainvoke(...)` (без runtime).
2. **Тестирует**: `app.agent.tools.skills :: make_load_skill_tool` (ветка дозагрузки индекса `_skill_context_index`).
3. **Суть**: Гарантирует, что `load_skill(skill_name)` при непустом namespace дописывает индекс документов формата `key: description` поверх обычного вывода, но никогда не раскрывает содержимое документа (двухуровневый progressive disclosure — тело тянется отдельным `get_skill_context`). Проверяет, что при пустом namespace выдача байт-в-байт совпадает с вызовом без runtime (секция индекса не появляется вовсе), что индекс ограничен загружаемым скиллом и владельцем (чужой скилл и чужой пользователь не просачиваются), и что форма с `file` и путь ошибки (неизвестный скилл) индекс не получают.
4. **Кейсы**:
   - непустой namespace → индекс `key: description` дописан, обычный вывод сохранён
   - индекс не содержит тело документа (`content` не просачивается)
   - пустой namespace → вывод идентичен вызову без runtime (нет секции `Skill Context:`)
   - без runtime → индекс не дописывается
   - индекс ограничен загружаемым скиллом (документ другого скилла не виден)
   - индекс изолирован по пользователю (документ другого uid не виден)
   - форма `load_skill(skill, file)` → индекс не дописывается
   - неизвестный скилл (Error-строка) → индекс не приклеивается к ошибке

### `test_skill_context_checkpoint.py` — security-checkpoint SKILL_CONTEXT_WRITE

1. **Файл**: `backend/tests/skill_context/test_skill_context_checkpoint.py` — unit, без инфраструктуры (чтение enum, детекторов и загрузка `configs/security.yaml`).
2. **Тестирует**: `app.agent.security.types :: Checkpoint/direction_of`, `app.agent.security.config :: checkpoint_configs/load_security_config`, `detectors.canary/unicode :: applies_to`.
3. **Суть**: Гарантирует, что новый checkpoint существует как inbound-точка (запись — недоверенный вход), резолвится из поставляемого `security.yaml` с включённым классификатором и непустыми `description`/`specifics`, и что оба детерминированных детектора (canary, unicode) к нему применяются — симметрично прецедентам `CUSTOM_INSTRUCTIONS_WRITE`/`KS_WRITE_REST`.
4. **Кейсы**:
   - `direction_of(SKILL_CONTEXT_WRITE)` == INBOUND
   - конфиг резолвится: `classifier_enabled=True`, `description` и `specifics` непустые
   - `CanaryDetector.applies_to` содержит checkpoint
   - `UnicodeDetector.applies_to` содержит checkpoint

### `test_skill_context_service.py` — сервисный слой над Store

1. **Файл**: `backend/tests/skill_context/test_skill_context_service.py` — sociable-unit, реальный `InMemoryStore` + `StubGuard` из `packages/testing`.
2. **Тестирует**: `app.services.skill_context :: LangGraphSkillContextService` (`list_skill_contexts`, `get_document`, `update_document`, `delete_document`).
3. **Суть**: Гарантирует, что листинг группирует документы по скиллу, проставляет `in_library` по startup-реестру (true для скилла в библиотеке, false для удалённого) и отдаёт полные документы, изолируя по пользователю. Пиннит два свойства security-контракта записи, критичных для персистентной инъекции: при отсутствии документа сервис бросает 404 **до** обращения к guard (проверяется по пустому `guard.calls`), а при вердикте INJECTION блокирует запись и оставляет прежний документ нетронутым. Подтверждает, что CLEAN и SUSPICIOUS пропускают запись (гейтит только INJECTION), что `update`/`delete` на отсутствующем документе дают 404, а данные удалённого из библиотеки скилла остаются достижимыми.
4. **Кейсы**:
   - list: пусто → `[]`
   - list: группировка по скиллу + `in_library` (true/false), полные документы
   - list: изоляция по пользователю
   - get: возврат документа; отсутствующий → NotFoundError
   - get: достижимость документа скилла вне библиотеки
   - update: round-trip нового значения
   - update: отсутствующий документ → NotFoundError
   - update: отсутствующий документ не обращается к guard (`guard.calls == []`) 🔴
   - update: CLEAN → запись проходит и персистится
   - update: SUSPICIOUS → проходит без блокировки
   - update: INJECTION → SecurityPolicyViolationError, прежний документ сохранён 🔴
   - delete: удаление существующего; отсутствующий → NotFoundError

### `test_skill_context_routes.py` — REST CRUD /users/me/skill-contexts

1. **Файл**: `backend/tests/skill_context/test_skill_context_routes.py` — integration, `httpx.AsyncClient` поверх `ASGITransport`, аутентифицированная фикстура `current_user` (реальный Postgres под auth), `InMemoryStore` + опциональный `StubGuard` на `app.state` (локальный conftest).
2. **Тестирует**: `app.api.routes.skill_context` + `app.api.schemas.skill_context` поверх `LangGraphSkillContextService`.
3. **Суть**: Гарантирует REST-контракт из design-brief: листинг группирует по скиллам с `in_library` и полными документами (snake_case, ISO-даты, без конверта пагинации); GET item отдаёт 200/404; PUT правит только существующий документ (200), несуществующий даёт 404 без создания, а невалидное тело (отсутствие обязательного поля, превышение лимитов) — 422 validation. Пиннит security-путь на HTTP-границе: INJECTION → 422 problem+json с `reason`, прежний документ не изменён; `reason` несёт detection_layer, когда guard его атрибутирует; запись в несуществующий документ с инъекционным содержимым остаётся 404 (404 раньше checkpoint — классификатор не тратится). DELETE отдаёт 204/404. Формы problem+json (type-URN, статус) сверяются с нормами api.md.
4. **Кейсы**:
   - GET листинг пуст → `{"skills": []}`
   - GET листинг: группировка + `in_library` (true/false), полный документ, ISO-даты, snake_case
   - GET item: 200 с телом документа
   - GET item отсутствующий: 404 problem+json (`urn:learnflow:entity-not-found`)
   - PUT существующего: 200, значение обновлено, round-trip через GET
   - PUT несуществующего: 404 (нет create-via-PUT)
   - PUT INJECTION: 422 problem+json, `reason=skill_context_write`, прежний документ сохранён 🔴
   - PUT INJECTION с detection_layer: `reason=llm_classifier` 🔴
   - PUT несуществующего с INJECTION-содержимым: 404 раньше guard (порядок 404→checkpoint) 🔴
   - PUT невалидное тело (parametrize: нет content / нет description / description > 200 / content > 20 000): 422 validation
   - DELETE существующего: 204, затем GET → 404
   - DELETE отсутствующего: 404 problem+json

**Осознанно не покрываем автотестом:**

- Реальная классификация инъекций LLM-классификатором (точность вердикта на настоящих атаках) — это eval, не unit; недетерминированный вывод модели в CI-гейте даёт флак → ручной кейс `{T1.7}` + backlog-eval поверх этого механизма.
- Регистрация skill-context tools в `internal_tools`/`global_tools` и сборка `app.state.skill_names` на старте — glue-проводка в `main.py` (нет бизнес-ветвлений, только DI-склейка в lifespan, который под `ASGITransport` не запускается) → мягкий гейт glue + smoke/ручной кейс `{T1.6}` через живой стек.
- Runtime-checkpoint `tool_call_arg` над аргументами `save_skill_context` (add-time проверки самого агентского пути) — это существующий сквозной механизм security, покрытый тестами `tests/security/`; skill-context не вводит новой логики в этот шов → чужая суита (`tests/security/`), не дублируем.
- Прямой `asearch`-limit по namespace листинга (headroom 500) как SQL/Store-специфика на реальном PG-backed Store — `InMemoryStore` этой границы не проверяет, а масштаб (≤ 20×20) headroom заведомо покрывает → осознанно не покрыто (не repository-слой; тонкость Store-бэкенда, не нашей логики).

**Замеченные прод-баги (для fixer'а, сам не чиню):** нет — контракт design-brief и реализация T1 согласованы, все 63 автотеста зелёные с первого прогона.

### Layer 0: Automated gate

- [x] `make check` — ruff + mypy + import-linter (9/9) + arch-checker → **0 ошибок**. *(tester re-run: format 296 files ok, mypy 234+43+7 clean, contracts 9 kept / 0 broken, arch-checker passed).*
- [x] `make test-scope P=backend/tests/skill_context` — **63 passed** (unit + integration скоупа зелёные). *(tester re-run: 63 passed in 8.76s, Python 3.12.12).*

---

## Ручные кейсы + статусы

Узкий ручной хвост — то, что автотест не закрывает: сквозные агентские циклы через живую модель,
реальная инъекция через LLM-классификатор, e2e через UI. Статусы и run-log ведут tester и fixer.

### Layer 1: Трек T1 — backend через живой стек

- [ ] ⚠️ **DEFERRED (env)** `{T1.1}` 📊 Изоляция и персистентность в реальном Store. Поднять стенд (`make docker-up`); под user-a агентом (или прямым вызовом tool через дев-эндпоинт) сохранить документ `profile` для `tech-article-writing`; под user-b `GET /api/users/me/skill-contexts` → пусто; под user-a → группа с документом. Ожидание: документы изолированы по `user_id` в реальном PG-backed Store, не только в `InMemoryStore`. — Не прогнан: изолированный стенд поднять нельзя (host-порт 5432/6379 уже заняты контейнерами соседнего worktree feat-010; `.env`/`.env.local` в этом worktree нет — некуда указать `make dev`; per CLAUDE.md § Параллельная разработка занятый порт/чужой стенд — эскалация, не самораз­рулка). Автотест `test_skill_context_tools.py` изоляцию по `user_id`/`skill_name` пиннит на `InMemoryStore`; живой PG-контур остаётся за INTEGRATION_TEST.
- [ ] ⚠️ **DEFERRED (нет LLM-ключа)** `{T1.2}` Двухуровневый disclosure в реальном агентском цикле. В чате под user-a попросить агента загрузить скилл `tech-article-writing` (при сохранённом `profile`). Ожидание: в tool-ответе `load_skill` виден индекс `Skill Context:` с `profile: <description>`, но не тело документа; тело появляется только после явного `get_skill_context`. — Не прогнан: агентский цикл требует реального LLM (`llm_api_key` пуст, в окружении только `ASSEMBLYAI_API_KEY`); плюс живой стенд заблокирован (см. T1.1). Логика дозагрузки индекса и не-просачивания тела закрыта `test_load_skill_context_index.py` (8 зелёных); живой цикл — INTEGRATION_TEST.
- [ ] ⚠️ **DEFERRED (env)** `{T1.3}` REST CRUD руками. Через `curl`/HTTP-клиент под токеном user-a: `GET` листинг → `PUT` существующего документа (200) → `GET` item (новое значение) → `PUT` несуществующего (404) → `DELETE` (204) → повторный `GET` (404). Ожидание: коды и формы problem+json совпадают с design-brief. — Не прогнан: живой стенд заблокирован (см. T1.1), а PUT-200-путь дополнительно требует CLEAN-вердикта от SecurityGuard-классификатора (нет LLM-ключа). REST-контракт (коды 200/404/422/204, problem+json, порядок 404→checkpoint) целиком закрыт `test_skill_context_routes.py` (15 зелёных, integration поверх реального Postgres под auth); ручной curl — INTEGRATION_TEST.
- [ ] ⚠️ **DEFERRED (env)** `{T1.4}` `in_library=false` для удалённого скилла. Сохранить документ под скилл, затем убрать скилл из библиотеки (удалить директорию скилла) и перезапустить backend. Ожидание: `GET` листинг показывает группу с `in_library=false`, документ читаем/удаляем через REST; в новой сессии агент этот контекст не подгружает (некому вызвать `load_skill`). — Не прогнан: живой стенд заблокирован (см. T1.1). `in_library` true/false по startup-реестру закрыт `test_skill_context_service.py`/`test_skill_context_routes.py` (листинг + достижимость документа вне библиотеки); живой restart-цикл — INTEGRATION_TEST.
- [ ] ⚠️ **DEFERRED (env)** `{T1.5}` 🔴 Лимит документов на живом Store. Сохранить 20 документов для одного скилла, попытаться сохранить 21-й новый key. Ожидание: отказ агентского tool с сообщением о лимите; upsert одного из 20 существующих проходит. — Не прогнан: живой стенд заблокирован (см. T1.1); прямой прогон tool против PG-Store потребовал бы записи в БД соседнего worktree (feat-010) — не делаю. Логика лимита (21-й new key отклонён, upsert на пределе разрешён) закрыта `test_skill_context_tools.py` на `InMemoryStore`; специфика PG-backed `asearch`-limit (headroom 21/500) осознанно вне автотестов (см. «Осознанно не покрываем») → живой PG-контур в INTEGRATION_TEST.
- [ ] ⚠️ **DEFERRED (env) — glue подтверждён инспекцией** `{T1.6}` Регистрация tools и реестра на старте. После `make dev` проверить, что `save/get/delete_skill_context` доступны агенту (граф собирается без ошибок) и `app.state.skill_names` заполнен (косвенно — через работающий `in_library`). Ожидание: startup-склейка `main.py` работает (покрывает осознанно-не-автотестенный glue). — Живьём не прогнан (стенд заблокирован, см. T1.1). Статическая верификация glue в `main.py` (lifespan): `scan_skill_names(skills_dir)` (стр. 338) → `app.state.skill_names` (339) → `make_skill_context_tools(skill_names)` (340), включены в `internal_tools` (352) и `global_tools` (442); `app.include_router(skill_context.router, ...)` (617). Все точки склейки присутствуют и корректны; `skills/tech-article-writing/SKILL.md` в библиотеке есть. Живое исполнение lifespan (граф собирается, `app.state.skill_names` наполнен) — INTEGRATION_TEST.

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [ ] Живой стек «REST ↔ агент»: документ, сохранённый агентом (`save_skill_context`), виден в `GET /api/users/me/skill-contexts` и наоборот — отредактированный через `PUT` документ агент читает обновлённым через `get_skill_context` в следующей сессии.
- [ ] 🔴 Реальная инъекция через LLM-classifier: `PUT` документа с настоящим инъекционным содержимым (override/role-switch/раскрытие системного промпта) при включённом классификаторе (реальный ключ) → 422 `security-policy-violation`; легитимная персонализация (voice/style) → 200. Проверяет качество вердикта на checkpoint `skill_context_write` (eval-природа, вне CI-гейта).

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] 👤 **DEFERRED** `{T1.7}` Полный агентский цикл через UI: пользователь ведёт диалог, агент процедурой (напр. voice-profile-builder) вызывает `save_skill_context`, затем в новой сессии `load_skill` подтягивает индекс и `get_skill_context` — тело; UI-секция «Контекст скиллов» (трек T2) отображает документ. Требует живой модели и браузера — эскалация тестировщику/архитектору. — Не прогнан: нужен живой LLM (ключа нет), браузер и код T2 (frontend) — E2E-кейс явно вне TEST(track), в INTEGRATION_TEST после барьера. Эскалирую архитектору.

---

## Находки ревью [severity+owner]

> Пишет **test-reviewer** (adversarial-ревью тестов против контракта, read-only). Чисто — секция пустая.

R1 minor [test] test_skill_context_service.py:56-76 / test_skill_context_routes.py:59-88 — сортировка в `list_skill_contexts` (документы внутри группы по `created_at`, группы по `skill_name`, service.py:110-116) нигде не проверена: и service-, и route-листинг сеют по одному документу на скилл и читают результат через dict по `skill_name` (`by_name`/`groups`), что игнорирует порядок. Реальная логика сортировки — непокрытая ветка. → добавить кейс с 2+ документами в одной группе и 2+ группами, ассерт на порядок списка (не dict-lookup). Низкий риск (детерминированный sort на маленькой модели), не блокирует.

R2 info [test] test_skill_context_tools.py:45-52 / test_load_skill_context_index.py:59-62 — tools прогоняются прямым `tool.coroutine(**kwargs)` с duck-typed `SimpleNamespace(store, context)` в обход `.ainvoke`/ToolNode (публичного шва инъекции runtime). Это оправдано механикой injected-`ToolRuntime` (полный ToolNode тяжелее, а `.ainvoke` без runtime и так проверяется в load_skill-кейсах) и совпадает с выбором «Дизайна автотестов»; ассерты — на состояние Store (наблюдаемый эффект), не на приватности. Претензии нет, фиксирую как осознанный компромисс.

Чисто: blocker — 0, major — 0, minor — 1 (R1, coverage-gap на сортировке листинга), info — 1 (R2). False-green не обнаружено: все ассерты содержательны и сверены с фактическим контрактом — URN-коды (`entity-not-found`/`security-policy-violation`/`validation-error`, exceptions.py:29/47 + problem.py), fallback `reason="skill_context_write"` и проброс `detection_layer.value` (service.py:176-182), лимиты 200/20000/20 и граница `>`/`>=` (tools + schemas), reject-регекс `^[a-z0-9_-]+$` (skills.py:14) — все пять bad_name отвергаются как invalid-name, не enshrined. StubGuard duck-типизирует `SecurityGuard.check` точно по сигнатуре (fakes.py:148-176), `.calls == []` — легитимная проверка security-контракта «404 раньше guard» (§ agent), не «проверка вызова вместо результата». Инфра по слою корректна: реальный Postgres только под auth-фикстурой `current_user`, skill-context — на `InMemoryStore`/`app.state`; unit-слои без БД. Изоляция: свежий `InMemoryStore` и function-scoped `configured_app`/`api_client` на каждый тест, loop-scope согласован, сети/LLM нет. Целостность A6: диф тестов ограничен `backend/tests/skill_context/` (5 файлов + локальный conftest); корневой `backend/tests/conftest.py` и прод-файлы скоупа тест-автором не тронуты (модификации прод в git status — имплементера, не тест-автора).
