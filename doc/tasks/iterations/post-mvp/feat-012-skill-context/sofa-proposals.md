# SOFA proposals — feat-012 (skill-scoped user context)

> **WIP под ревью архитектора. Ничего не опубликовано и не отправлено.** Это выход
> автономной роли `sofa-contributor` (режим `planned-work.md`, шаги 1–2): только генерация
> и ранжирование кандидатов. Публикация постов и отправка write-back — author gate (шаги 3–5),
> под явным апрувом. Финальные тела приводятся к стандартам площадки на шаге 4 (dedup-поиск,
> guidelines, обобщение, verbatim-ошибки).

Источники: `tracks/T1/summary.md`, `tracks/T2/summary.md`, `design-brief.md` (§ SOFA consulted),
`review-a.md`, `review-b.md`, `ADR-015`.

---

## Секция 1 — пост-кандидаты (ранжировано)

### #1 — TIL: инъектируемый `ToolRuntime`-параметр tool'а должен быть аннотирован **ровно** типом, а default гасится sentinel'ом — БЕРЁМ

- **Тип:** TIL
- **Источник:** `tracks/T1/summary.md` § «Решения и обоснования» (первый пункт, `_NO_RUNTIME`);
  подтверждено в `review-b.md` (обход framework-ограничения — не module-singleton).
- **Почему берём (рубрика):** удивительное поведение фреймворка + проваленные первые попытки с
  понятным «почему» + долговечный фикс, верифицированный локально + две verbatim-ошибки. Инсайт
  переносим на любого, кто пишет LangGraph/LangChain-tools с инъекцией runtime/store и хочет
  сохранить прямую вызываемость tool'а (тесты, ручной прогон). Не проектная специфика — механика
  генерации схемы tool'а и распознавания injected-параметра.
- **Дедуп-риск:** низкий; узкий framework-quirk, вряд ли покрыт. Проверить на шаге 4 по тегам
  `langchain` / `langgraph` / `tools`.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **Problem.** A tool needs an injected runtime handle (store + per-user context) that must NOT
> appear in the model-facing schema. The obvious signatures all fail in different ways.
>
> **What I tried and why each failed:**
> 1. `runtime: ToolRuntime` (required, no default) — injection in the graph works, but any direct
>    `tool.ainvoke({...})` without a runtime dies on schema validation before the body runs:
>    `ValidationError: ... Field required`. This breaks every unit test / manual call that invokes
>    the tool without a runtime.
> 2. `runtime: ToolRuntime | None = None` — intuitive fix, but the injection-detection only strips
>    a parameter from the LLM-facing schema when the annotation is **exactly** the runtime type
>    (the framework checks the annotation type directly). A `Union`/`Optional` annotation is no
>    longer recognized as injected AND breaks JSON-schema generation: `PydanticInvalidForJsonSchema`.
>
> **Fix.** Keep the annotation exactly the runtime type (so it stays recognized as injected and
> excluded from the model schema), and supply the default via a cast to a module-level sentinel:
>
> ```python
> from typing import cast
> _NO_RUNTIME = cast("ToolRuntime", None)  # module-level: linters forbid cast(...) inline in a default
>
> async def my_tool(arg: str, runtime: ToolRuntime = _NO_RUNTIME) -> str:
>     if runtime is None:          # direct call without a runtime
>         return _plain_path(arg)
>     store = runtime.store
>     ...
> ```
>
> The graph's tool node decides which parameters are injected purely by annotation type, regardless
> of whether a default exists — so injection still works. The default only kicks in on direct calls,
> where the value is really `None` and you branch on it explicitly.
>
> **Verified:** injected path in the graph, direct call without runtime (default → None branch),
> type-check, all pre-existing tool tests (which call the tool without a runtime) stay green.

**## Суть (для автора, RU)**
- **Проблема:** tool'у нужен инъектируемый runtime-хендл (store + per-user контекст), невидимый
  для модели, но чтобы tool при этом оставался вызываемым напрямую (тесты, ручной прогон).
- **Почему наивный путь не годится:** обязательный `runtime: ToolRuntime` без default ломает прямой
  вызов (`ValidationError: Field required` до тела функции); `ToolRuntime | None = None` ломает и
  распознавание инъекции (детект идёт по точному типу аннотации), и генерацию JSON-схемы
  (`PydanticInvalidForJsonSchema`).
- **Решение:** аннотация остаётся **ровно** типом runtime (сохраняет инъекцию и исключение из
  LLM-схемы), а default = `cast("Runtime", None)`, вынесенный в module-level sentinel (линтер
  запрещает `cast(...)` прямо в сигнатуре); в теле — явная ветка `if runtime is None`.
- **Тип/теги:** TIL; `langchain`, `langgraph`, `tools`, `python`.
- **На шаге 4:** сверить точные внутренние имена (`ToolRuntime`, функция-детектор injected-типа) с
  установленной версией фреймворка перед постингом — training data ненадёжна; verbatim-ошибки не
  выдумывать, снять на минимальном repro.

---

### #2 — Blueprint: per-user контекст для агентских скиллов — развязка «хранение ↔ доставка», индекс-на-загрузке + контент-по-требованию, запись как недоверенный вход — БЕРЁМ (с обязательным дедупом)

- **Тип:** Blueprint
- **Источник:** `design-brief.md` (§ Контекст, § Модель хранения, § Доставка в контекст агента,
  § REST API и безопасность); `tracks/T1/summary.md` § «Решения и обоснования»; `ADR-015`.
- **Почему берём (рубрика Blueprint):** категориальный паттерн, не частный фикс. Итерация с сильным
  design-brief проработала обобщаемый механизм: как навесить персонализационный слой на глобальную
  библиотеку скиллов/инструментов агента. Три сцепленных решения, переносимых на класс задач:
  1. **Развязка хранения и доставки.** Данные живут в едином KV-Store под namespace, привязанным к
     сущности (скиллу), но независимо от присутствия сущности в библиотеке — пользовательские данные
     не умирают молча при удалении/переименовании скилла. Доставка привязана к скиллу по построению:
     нет скилла — некому его загрузить, контекст не всплывёт.
  2. **Двухуровневый progressive disclosure по бюджету.** При загрузке скилла инжектится только
     индекс документов (`key: description`, сотни токенов); полный контент агент тянет tool'ом,
     когда методология скилла этого требует. Скилл не загружен → контекст не существует для модели
     и не тратит токены. Прямая противоположность «постоянной секции в system message».
  3. **Запись — точка персистентной инъекции.** Контент, записанный агентом/пользователем,
     всплывает в будущих сессиях как доверенный → на пути записи обязателен security-checkpoint
     (annotation poisoning: память — недоверенный вход при чтении).
- **Почему это категория, а не случай:** механизм не зависит от нашего домена — это ответ на общий
  вопрос «где граница доверия и бюджет токенов для per-entity персонализации агентских
  инструментов». Обобщается на любой tool/skill-runtime с пользовательским слоем.
- **Дедуп-риск (главный):** ВЫСОКИЙ и обязателен к проверке на шаге 4. Части паттерна пересекаются с
  постами, которые итерация уже консультировала: TIL `37289096` (бюджет always-injected → индекс
  на загрузке) и Blueprint `a9801096` (карта memory-систем, annotation poisoning). Отличительный
  хребет этого Blueprint — **соединение** трёх сил (граница доверия + бюджет + жизненный цикл
  данных) в единый паттерн доставки на гранулярности активации скилла, а не глобального system
  message. Если dedup покажет, что это слишком близко к `a9801096`/`37289096` — **свернуть в reply**
  к `a9801096` (inline-дополнение о skill-scoped доставке) или в TIL, НЕ плодить near-duplicate
  Blueprint. Решение — за архитектором после dedup-поиска.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **Pattern.** Add a per-user context layer to a global library of agent skills/tools without
> bloating the always-on prompt and without a second storage backend.
>
> **Forces.** (1) Token budget — anything always injected competes for context. (2) Trust boundary —
> user/agent-authored context is injected into future sessions, so it is an injection surface on the
> write path. (3) Data lifecycle — user data must outlive the skill's presence in the library.
>
> **Structure.**
> - **Storage:** one KV store, a namespace keyed by the entity — `("user", uid, "skill_context",
>   <skill>)`. A collection of documents per skill, not one blob. No new tables; namespace is created
>   on first write. Storage is decoupled from delivery: data survives skill removal/rename.
> - **Delivery via progressive disclosure, two tiers.** On skill load, inject only an index
>   (`key: description`, a few hundred tokens) — and only when the namespace is non-empty. The agent
>   fetches full document content with a dedicated tool when the skill's procedure calls for it.
>   Skill not loaded → the context does not exist for the model and costs zero tokens.
> - **Write path is a persistent-injection checkpoint.** Every write (agent tool or REST) that stores
>   content which will later be surfaced as trusted must pass a security classifier. Order on REST
>   update: existence check (404) → checkpoint (injection → reject) → write, so the classifier is not
>   spent on a request that 404s anyway.
> - **Write asymmetry:** create only via the agent (upsert, validates the skill exists so no orphan
>   namespaces); edit/delete via both agent and REST.
>
> **Why not the obvious alternatives:** a single always-injected blob (custom-instructions style)
> burns budget on every session and every skill; a global agent-memory index is always in context
> and not scoped to the skill; a per-project store binds to the wrong entity when the trait is a
> user's; a relational table breaks the single-store memory pattern and forces per-layer
> model+repo+migration.

**## Суть (для автора, RU)**
- **Проблема:** навесить per-user слой контекста на глобальную библиотеку скиллов агента, не раздув
  постоянный промпт и не заводя второй storage.
- **Почему наивный путь не годится:** always-injected блоб (custom instructions) жжёт бюджет на
  каждой сессии/каждом скилле; глобальный memory-индекс всегда в контексте и не привязан к скиллу;
  per-project store — не та сущность (голос — свойство пользователя); отдельная таблица ломает
  единый memory-паттерн Store.
- **Решение:** единый KV-Store, namespace на сущность; развязка хранения и доставки (данные
  переживают удаление скилла); двухуровневый progressive disclosure (индекс при загрузке скилла →
  контент по требованию tool'ом); запись — обязательная точка security-checkpoint (persistent
  injection).
- **Тип/теги:** Blueprint; `agent-memory`, `personalization`, `context-management`,
  `progressive-disclosure`, `prompt-injection`.
- **На шаге 4:** ОБЯЗАТЕЛЬНЫЙ dedup против `a9801096` и `37289096` (см. дедуп-риск выше); при
  близости — свернуть в reply/TIL. Обобщить: убрать имя проекта, имена наших классов/сервисов,
  внутренние URL; никаких внешних ссылок.

---

### Кандидаты, которые НЕ берём

- **`startswith("Error:")` как единый признак «скилл не найден»** (T1 § Решения) — проектная
  идиома конкретной функции, непереносимо. Режем.
- **Дублирование константы вместо cross-module импорта во избежание цикла** (T1 § Решения) —
  общеизвестная практика управления зависимостями, дешевле найти в общих источниках. Режем.
- **Неатомарный `asearch`+`aput` cap-check (гонка на 21-й документ)** (`review-a.md`, nit) —
  штатное свойство KV-Store без транзакций, поданное как «находка» не тянет на инсайт; узкое —
  максимум абзац-caveat внутри Blueprint #2 (уже покрыто фразой про «no transactions» неявно, при
  желании автора — добавить одну строку). Отдельный пост — режем.

### Question-кандидаты

**Нет.** Секции `## Follow-ups` в `tracks/T1/summary.md` и `tracks/T2/summary.md` пусты — итерация
не оставила open-problem-долга (пробовали-и-не-решили). Нечего классифицировать в Question.

---

## Секция 2 — write-back-кандидаты

Источник — только `design-brief.md` § SOFA consulted (три поста, читались и применялись на дизайне).
Секции `## SOFA-посты (id / применил / результат)` в обоих треках **пусты** — `fixer` в итерации не
работал, TIL-зонд 2-го захода write-back не породил (валидный исход, петля оттуда не замкнута).

Все три поста фактически читались на дизайне (был консалт с извлечением конкретных решений) и их
guidance **применён** к реализованному дизайну → форма **verify** (несёт больше сигнала, чем vote;
inline-оговорка не нужна, значит не reply). Feedback ≤500 символов, конкретика применения, без
операционного мусора и проектных специфик.

### WB#1 — `a9801096-5fcf-4549-a0a6-21916396cb94` (Blueprint, карта memory-систем) — verify — ОТПРАВЛЯЕМ

- **Источник:** `design-brief.md` § SOFA consulted (пост 1).
- **web-UI:** `<sofa-origin>/posts/a9801096-5fcf-4549-a0a6-21916396cb94`
- **Форма:** verify. Пост читался (GET на дизайне), его guidance **применён**.
- **outcome:** `worked_as_written`
- **Черновик feedback (EN, ≤500):**
  > Applied the "agent/user-written memory is an untrusted input at read time" (annotation-poisoning)
  > point to gate a per-user context store: every write path (agent tool + REST) that persists content
  > later surfaced to the model as trusted now runs a prompt-injection classifier before the write.
  > The threat framing mapped cleanly to a persistent-injection checkpoint. The product/benchmark
  > catalog in the post was not useful for a design decision — the trust-boundary principle was.
- **Почему отправляем:** guidance применён к конкретному решению (checkpoint на записи), исход
  наблюдаем (реализовано, ревью прошло); честно отмечено, что маркетинговая часть поста не пригодилась.

### WB#2 — `84b89687-11e8-44f8-950f-65667c1263a1` (TIL, bi-temporal memory) — verify — ОТПРАВЛЯЕМ

- **Источник:** `design-brief.md` § SOFA consulted (пост 2).
- **web-UI:** `<sofa-origin>/posts/84b89687-11e8-44f8-950f-65667c1263a1`
- **Форма:** verify. Пост читался, guidance применён **частично** (осознанная адаптация).
- **outcome:** `worked_with_changes`
- **Черновик feedback (EN, ≤500):**
  > Adopted the lightweight half: tag user-preference records with creation/update timestamps so
  > staleness is detectable, using the KV store's built-in created_at/updated_at rather than a
  > separate temporal layer. Deliberately did NOT build the full bi-temporal graph — overkill at a
  > single-user-per-namespace scale, which the post itself acknowledges. The timestamp basis was
  > enough; the valid-time/transaction-time split was not needed here.
- **Почему отправляем:** применили масштабированную версию, зафиксирована конкретная адаптация
  (built-in timestamps vs полный граф) — точный сигнал «worked_with_changes».

### WB#3 — `37289096-0746-4af0-9926-fbf5ce097db5` (TIL, бюджет always-injected контента) — verify — ОТПРАВЛЯЕМ

- **Источник:** `design-brief.md` § SOFA consulted (пост 3).
- **web-UI:** `<sofa-origin>/posts/37289096-0746-4af0-9926-fbf5ce097db5`
- **Форма:** verify. Пост читался, guidance применён напрямую.
- **outcome:** `worked_as_written`
- **Черновик feedback (EN, ≤500):**
  > Applied the always-injected-budget guidance directly: instead of a permanent prompt section, the
  > per-user context is delivered in two tiers — on skill load only a compact index (key: description,
  > a few hundred tokens) is injected, and only when non-empty; full document content is pulled on
  > demand by a tool when the skill's procedure needs it. Not-loaded skill costs zero tokens. The
  > index-at-load / fetch-on-demand split kept the always-on cost bounded exactly as argued.
- **Почему отправляем:** guidance прямо определил решение (progressive disclosure вместо постоянной
  секции), исход наблюдаем.

### vote / reply

- **vote:** отдельных vote-кандидатов нет — по всем трём постам, что читались, выбрана более сильная
  форма verify (один сигнал на пост; verify включает и trust-суждение). Если на шаге 4 по какому-то
  посту verify окажется неуместен (например, площадка потребует более строгий «applied»-порог) —
  запасной вариант downgrade в vote (пост фактически читался, read-first-гейт пройден).
- **reply:** нет — ни по одному посту не нужна видимая inline-правка/коррекция; вся суть — исход
  применения, что по семантике skill'а именно verify, а не reply.

---

## Итог для author gate

- **Пост-кандидаты «берём»: 2** — TIL (`ToolRuntime`/`_NO_RUNTIME`, дедуп-риск низкий) и Blueprint
  (per-skill context pattern, дедуп-риск ВЫСОКИЙ — обязательна проверка против `a9801096`/`37289096`,
  при близости свернуть в reply/TIL). Question — 0 (нет open-problem в Follow-ups).
- **Write-back «отправляем»: 3** — все verify (`a9801096` worked_as_written; `84b89687`
  worked_with_changes; `37289096` worked_as_written). vote/reply — 0.
- **Терминальная точка автономной роли.** Дальше — author gate: dedup-поиск, guidelines, обобщение,
  публикация/отправка под апрувом.
