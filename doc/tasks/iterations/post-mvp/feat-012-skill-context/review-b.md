# Code Review Report — режим B (соответствие контракту)

Итерация: feat-012 (skill-scoped user context). Diff: `git diff develop...HEAD`.
Зона режима B — суждение о смысле конвенций и намерении кода; детерминированно
покрытое (import-linter, arch-checker, mypy, ruff, ESLint/FSD, Prettier — всё
зелёное по arch-checker-report) не перепроверялось.

### Summary
- blocker: 0
- nit: 1
- pre-existing: 1

### Вердикт

Изменение соответствует контракту. Backend (T1) и frontend (T2) реализованы по
design-brief дословно и симметрично прецеденту `user_memory` (сервис/схемы/роут/tools
на бэке, `shared/api` + секция на `/settings` на фронте). Все запиненные формы —
namespace `("user", uid, "skill_context", <skill>)`, тела REST, порядок проверок на
PUT (404 → checkpoint → aput), лимиты (200/20 000/20), двухуровневый progressive
disclosure в `load_skill` — воспроизведены точно. Новый checkpoint
`SKILL_CONTEXT_WRITE` заведён по образцу `KS_WRITE_REST`/`CUSTOM_INSTRUCTIONS_WRITE`
(INBOUND, оба детектора, `classifier_enabled: true`). Агентский путь записи опирается
на runtime-checkpoint `tool_call_arg` — подтверждено: новые tools попадают в
`internal_tools` → `collect_fragment_corpus`/`collect_tool_registry` (`main.py:349–364`),
как и предписывает design-brief § Инструменты агента.

### Замечания

| Severity | Намерение | Файл:строка | Норма (ссылка) | Замечание | Предложение |
|---|---|---|---|---|---|
| nit | REST update поднимает актуальные таймстемпы | `backend/app/services/skill_context.py:756–759` | conventions § Обработка ошибок (наблюдаемость/консистентность) | После `aput` делается повторный `get_document` (ещё один `aget`) вместо сборки ответа из входных полей + `existing.created_at`. Обоснование в summary («единственный источник истины для `updated_at`») валидно; отмечаю лишь как осознанный лишний round-trip, не дефект. | Оставить как есть — trade-off задокументирован и корректен. |
| pre-existing | Guard резолвится best-effort | `backend/app/api/routes/skill_context.py:375` | design-brief § REST «Checkpoint обязателен» | `guard=getattr(request.app.state, "security_guard", None)`: при отсутствии guard на `app.state` PUT прошёл бы без проверки. На практике Sec 2.0 всегда сконструирован в lifespan до старта роутеров; паттерн дословно скопирован из `user_memory.py:19`/`sphere`. Не регресс, не вводится этой итерацией. | Ничего не менять в рамках feat-012; при желании ужесточить — отдельным решением по всем write-роутам сразу. |

### Blocker без прецедента в conventions

Нет.

### Незамеченный дрейф документации (для docs-updater)

Дрейф ожидаемый, не «незамеченный»: T1/T2 по design-brief § Партиция треков не
трогают `doc/**` (кроме `tracks/`), вся doc-актуализация вынесена в фазу DOC_UPDATE
после барьера. Фиксирую конкретную поверхность, которую DOC_UPDATE должен покрыть —
новый публичный контракт нигде в постоянной доке пока не отражён (`grep` по
`doc/tech/` даёт ноль совпадений на `skill_context`):

- **ADR-015** (`doc/tech/adr/ADR-015-unified-memory-backend.md:21–23`) — список
  namespace'ов Store; добавить четвёртый:
  `("user", uid, "skill_context", <skill>)`.
- **`doc/tech/user-memory.md:79–88`** — таблица namespace'ов памяти дублирует тот же
  список; синхронизировать с ADR-015.
- **`doc/tech/agent-runtime.md`** — новые tools `get/save/delete_skill_context` и
  дозагрузка индекса контекста в `load_skill` (progressive disclosure) не описаны.
- **`doc/tech/backend.md`** — новый REST-ресурс `/users/me/skill-contexts`
  (листинг с группировкой/`in_library`, GET/PUT/DELETE item) и сервис
  `LangGraphSkillContextService`.
- **`doc/tech/frontend.md`** — секция «Контекст скиллов» на `/settings`, API-слой
  `shared/api/skill-context.ts`.
- **Security-документация** (модель угроз / список checkpoint'ов, если ведётся) —
  новый checkpoint `SKILL_CONTEXT_WRITE` как третья точка персистентной инъекции.

### Проверенные контрактные точки (без замечаний)

- Формы тел REST (листинг с `skills[]`/`in_library`/полными документами; item-объект;
  PUT body `{description, content}` → объект документа) — совпадают с design-brief §
  REST дословно; frontend DTO зеркалят их (snake_case, `content` в листинге,
  `updated_at`).
- Порядок проверок на PUT: `aget`(404) → guard `SKILL_CONTEXT_WRITE`(INJECTION→422) →
  `aput` — короткое замыкание на 404 (classifier не тратится) реализовано.
- Guard-блок (`security_event=True`, keyword-поля `checkpoint`/`verdict`/`identifiers`/
  `metadata.detection_layer`, `SecurityPolicyViolationError(reason=detection_layer)`) —
  байт-в-байт структурно совпадает с `user_memory.update_instructions`; § Logging
  соблюдён.
- Роуты без `try/except` — доменные `NotFoundError`/`SecurityPolicyViolationError`
  маппятся глобальным `AppError`-handler; § Обработка ошибок (исключения, не HTTP в
  домене) соблюдён.
- Лимиты: Pydantic `Field(max_length=...)` на REST + plain-проверки в tool (error-строки
  по прецеденту `knowledge_sphere`) — симметричная двойная валидация, как предписано.
  Осознанное дублирование констант (не cross-module импорт) обосновано разделением
  слоёв; согласуется с § Env vs константы (бизнес-инварианты в коде).
- `load_skill`: индекс дописывается только при найденном скилле и непустом namespace;
  `file`-форма и ошибка не меняются; содержимое документов не просачивается (только
  `key: description` через `format_index`). Обход framework-ограничения `runtime`
  (`_NO_RUNTIME`-sentinel) — не module-singleton (неизменяемая typed-константа),
  жёсткое правило не нарушено.
- FSD: API-слой в `shared/api/skill-context.ts` (по прецеденту `user-memory.ts`),
  секция и под-компоненты в `pages/user-settings/ui` — публичный API слайса не тронут;
  мутации инвалидируют `queryKeys.skillContexts`; 422 → `isSecurityViolation` +
  `SECURITY_VIOLATION_MESSAGE`, как у «Своих инструкций». § frontend (состояние,
  мутации, токены) соблюдён.
