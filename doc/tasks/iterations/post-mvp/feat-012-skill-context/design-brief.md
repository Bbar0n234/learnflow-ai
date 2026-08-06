# Design Brief: feat-012 — Skill-scoped user context

## Контекст

Скиллы — глобальная библиотека, одинаковая для всех пользователей; персонализационного слоя над ними нет. Первый реальный запрос на такой слой — профиль авторского голоса скилла `tech-article-writing` (перенесён в feat-009): README скилла требует, чтобы в мультипользовательском продукте профиль жил в per-user хранилище и приходил в скилл извне, а не лежал в коде скилла.

Обобщение (решение архитектора): у **любого** скилла может быть per-user коллекция документов — «контекст скилла» (профили стиля, образзы, предпочтения). Профиль голоса — первый случай; будущие: предпочтения вёрстки слайдов, стиль визуализации и т.п.

## Модель хранения

Четвёртый namespace в LangGraph Store — единый паттерн расширения памяти (ADR-015):

```
("user", uid, "instructions")                — custom instructions   [есть]
("user", uid, "memory")                      — заметки агента        [есть]
("project", pid, "sphere")                   — Knowledge Sphere      [есть]
("user", uid, "skill_context", <skill_name>) — НОВОЕ
```

Namespace = «директория» скилла, key = имя документа (`profile`, `sample-habr-sofa`, …), value = `{description, content}`. Коллекция, не единственный блоб: профиль + дополнительные образцы — требование методологии скилла.

Отклонённые альтернативы: custom instructions (один блоб, висит в контексте всех сессий), user memory (нет привязки к скиллу, индекс всегда в контексте), Knowledge Sphere (per-project, а голос — свойство пользователя), SQLAlchemy-таблица (ломает единый паттерн памяти ADR-015; cleanup при удалении пользователя решается одинаково для всех неймспейсов Store).

## Доставка в контекст агента

Ключевое решение: контекст доставляется **через `load_skill`, а не постоянной секцией system message**.

```mermaid
sequenceDiagram
    participant A as Agent
    participant LS as load_skill
    participant SC as get_skill_context
    participant ST as Store

    A->>LS: load_skill("tech-article-writing")
    LS->>ST: asearch(("user", uid, "skill_context", skill))
    LS-->>A: SKILL.md + индекс контекста<br/>(key: description, ~сотни токенов)
    Note over A: скилл дошёл до voice-прохода
    A->>SC: get_skill_context(skill, "profile")
    SC->>ST: aget(...)
    SC-->>A: полное содержимое документа
```

Двухуровневый progressive disclosure: при `load_skill` — только индекс документов; содержимое агент тянет tool'ом, когда методология скилла этого требует. Не загружен скилл → контекст не существует для модели и не тратит токены. Пустой namespace → секция индекса не дописывается вовсе (выдача `load_skill` без документов не меняется).

Развязка хранения и доставки решает вопрос жизненного цикла: данные в Store живут независимо от наличия скилла в библиотеке (пользовательские данные молча не умирают при удалении/переименовании скилла), а доставка привязана к скиллу по построению — нет скилла, некому вызвать `load_skill`.

## Инструменты агента

Доменные tools по образцу user memory (решение «общие tools над всем Store» отклонено: описания-монстры, потеря типовой семантики, хуже гардрейлы):

- `get_skill_context(skill_name, key)`
- `save_skill_context(skill_name, key, description, content)` — upsert; путь создания документов (создаёт агент, например процедурой voice-profile-builder)
- `delete_skill_context(skill_name, key)`

`save_skill_context` проверяет существование скилла в библиотеке: запись под несуществующее или опечатанное имя отклоняется, осиротевшие namespace не создаются. Отдельного add-time checkpoint у агентского пути записи нет — аргументы tools уже покрыты runtime-checkpoint `tool_call_arg` (симметрично memory-tools).

## REST API и безопасность

- `GET /users/me/skill-contexts` — группировка по скиллам; у группы флаг `in_library` (для бейджа в UI); источник флага — индекс скиллов, собранный на старте приложения
- `GET /users/me/skill-contexts/{skill_name}/{key}` — 200 / 404
- `PUT /users/me/skill-contexts/{skill_name}/{key}` — правка **только существующего** документа: полная замена значения, `description` и `content` обязательны; несуществующая пара `(skill_name, key)` → 404. Создание через REST не предусмотрено: PUT-create отдал бы клиенту выбор URI и плодил осиротевшие записи; путь создания — агент.
- `DELETE /users/me/skill-contexts/{skill_name}/{key}` — 204 / 404

Форма тел (по прецеденту `user_memory`: полные документы в листинге, snake_case, даты ISO; пагинация-конверт не нужен — данные ограничены лимитами ниже):

```jsonc
// GET /users/me/skill-contexts
{ "skills": [ { "skill_name": "tech-article-writing", "in_library": true,
                "documents": [ { "key": "profile", "description": "…", "content": "…",
                                 "created_at": "…", "updated_at": "…" } ] } ] }
// GET item → объект документа (key, description, content, created_at, updated_at)
// PUT body → { "description": "…", "content": "…" }; ответ — объект документа
```

Порядок проверок на PUT: существование документа (404) → checkpoint SecurityGuard (новый, по образцу `CUSTOM_INSTRUCTIONS_WRITE`; INJECTION → 422) — classifier не гоняется по заведомо отклоняемому запросу. Checkpoint обязателен: контент инжектится агенту в каждой будущей сессии — точка персистентной инъекции.

Итоговая симметрия путей записи: создание — только агент (upsert в `save_skill_context`), правка — агент и REST, удаление — агент и REST.

### Лимиты

Бизнес-инварианты (живут в коде, не в env): `content` ≤ 20 000 символов; `description` ≤ 200 (строка индекса, инжектится при каждом `load_skill`); документов на скилл ≤ 20 (проверяется в `save_skill_context` при создании нового key, upsert существующего лимитом не ограничен). Валидация симметрична: Pydantic на REST, проверки в tools.

## UI

Секция «Контекст скиллов» на `/settings` (между «Памятью агента» и MCP). **Референс — интерактивный мокап: [mockups/settings-skill-context.html](mockups/settings-skill-context.html)** (вёрстка и токены воспроизведены из frontend/src; открывать локально в браузере).

Поведение из мокапа:

- Группировка по скиллу (имя моноширинным), внутри — документы: key + description.
- Клик по документу → отрендеренный Markdown-предпросмотр (скролл внутри превью при длинном контенте).
- «Править» → сырой Markdown в textarea; «Сохранить» (security-checkpoint, ошибка — как у «Своих инструкций») / «Отмена».
- Удаление документа. Создание из UI не предусмотрено — создаёт агент (паттерн «Памяти агента»).
- Скилл отсутствует в библиотеке → бейдж «скилла нет в библиотеке», данные и действия сохраняются.
- Пустое состояние: «Пока пусто. Скиллы будут сохранять сюда ваши профили и предпочтения по ходу работы».

## Связь с feat-009

`tech-article-writing` после переноса работает в режиме B (без профиля). Эта итерация даёт механизм; сам профиль голоса рождается процедурой `voice-profile-builder` после первой статьи, написанной через продукт, — данные появятся естественным путём, миграция данных не нужна.

## Scope boundaries

Не входит: бинарные документы контекста (референсные изображения — backlog, зависимость от `artifact_blobs` feat-010), создание документов пользователем из UI, просмотр содержимого самих скиллов (кандидат «страница библиотеки скиллов» — backlog, вместе с per-user включением скиллов, Фаза 5b), автоматическое накопление голоса из обратной связи (backlog, поверх этого механизма).

## Партиция треков

| Трек | Скоуп | Файловый скоуп |
|------|-------|----------------|
| T1 | Backend: Store namespace `skill_context`, tools `get/save/delete_skill_context`, индекс в `load_skill`, REST CRUD `/users/me/skill-contexts`, checkpoint SecurityGuard, автотесты backend | `backend/app/**` (agent/tools, agent/skills, agent/security, api/routes, api/schemas, services, repositories по необходимости), `configs/security.yaml` (блок нового checkpoint; файл бэкендовый, T2 не трогает), `backend/tests/skill_context/` |
| T2 | Frontend: секция «Контекст скиллов» на `/settings` по мокапу (группировка, Markdown-превью, правка raw, удаление, бейдж, пустое состояние), API-слой, тесты компонентов | `frontend/src/**` (pages/user-settings, shared/entities api-слой по FSD), тесты рядом с компонентами |

**Вердикт непересечения:** файловые скоупы дизъюнктны (`backend/**` vs `frontend/**`); общих файлов нет. REST-контракт, от которого зависит T2, зафиксирован в design-brief (§ REST API и безопасность) — T2 работает от контракта, не от кода T1.

Внутритрековые общие файлы (не кросс-трек, закреплены явно): за T1 — `backend/app/main.py`, `backend/app/api/routes/__init__.py`, `backend/app/agent/tools/__init__.py`, `backend/app/agent/security/types.py`, `backend/tests/conftest.py`; за T2 — `frontend/src/pages/user-settings/ui/SettingsPage.tsx`, `frontend/src/shared/api/query-keys.ts`.

**doc/`**` треки не трогают** (кроме своих `tracks/<id>/`): замеченный дрейф — строкой в `## Follow-ups` summary трека; вся doc-актуализация — фазой DOC_UPDATE после барьера.

**Параллельность фаз:** все per-track фазы T1 и T2 идут параллельно без ограничений (PLAN…TEST). Ручная проверка UI-кейсов T2 против живого backend — не в TEST(track), а в INTEGRATION_TEST после барьера (там доступен код T1).

## SOFA consulted

Прямых постов про skill-scoped user context нет (запросы: user memory, personalization, style profile, context injection, per-user, custom instructions; теги `memory`, `personalization`). Смежное:

- `a9801096-5fcf-4549-a0a6-21916396cb94` (Blueprint, карта memory-систем) — **annotation poisoning**: память, записанная агентом, — недоверенный вход при чтении. Взято как подтверждение security-checkpoint на записи skill-context (контент инжектится в будущие сессии). Продукты/бенчмарки из поста отвергнуты как маркетингово окрашенные.
- `84b89687-11e8-44f8-950f-65667c1263a1` (TIL, bi-temporal memory) — записи о предпочтениях пользователя помечать временем и детектировать устаревание. Взято частично: `created_at`/`updated_at` Store уже даёт основу; полный bi-temporal graph отвергнут — overkill для нашего масштаба (сам пост это признаёт).
- `37289096-0746-4af0-9926-fbf5ce097db5` (TIL) — бюджет always-injected контента: подтверждает решение «при load_skill — только индекс, содержимое по требованию».
