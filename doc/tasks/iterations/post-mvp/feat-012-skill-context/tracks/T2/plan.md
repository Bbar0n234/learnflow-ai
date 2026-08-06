# Implementation Plan: feat-012 / трек T2 — Frontend «Контекст скиллов» на /settings

## Контекст

Трек добавляет на `/settings` секцию «Контекст скиллов»: пользователь видит свои
per-user документы, сгруппированные по скиллу, раскрывает документ в отрендеренный
Markdown-предпросмотр, правит сырой Markdown, удаляет документ. Создание из UI не
предусмотрено — документы рождает агент. Скилл, которого больше нет в библиотеке,
помечается бейджем, но данные и действия сохраняются.

T2 работает **от REST-контракта design-brief** (§ REST API и безопасность), backend
(T1) пишется параллельно — в его код не заглядываем, живой backend доступен только в
INTEGRATION_TEST после барьера.

Источники:
- Запись итерации: `doc/tasks/tasklist-post-mvp.md` § feat-012 (критерии приёмки, строки 536–542)
- Design-brief: `doc/tasks/iterations/post-mvp/feat-012-skill-context/design-brief.md`
  (§ REST API и безопасность — запиненная форма тел; § UI; § Партиция треков — границы T2, строки 105–118)
- Мокап-референс: `doc/tasks/iterations/post-mvp/feat-012-skill-context/mockups/settings-skill-context.html`
- FSD-раскладка, состояние, мутации: `doc/tech/conventions/frontend.md`
- Прецедент: `frontend/src/pages/user-settings/` (`AgentMemorySection.tsx`,
  `CustomInstructionsSection.tsx`, `SettingsPage.tsx`), `frontend/src/shared/api/user-memory.ts`,
  `query-keys.ts`, `frontend/src/shared/ui/MarkdownRenderer.tsx`,
  `frontend/src/shared/lib/security-error.ts`

### Ключевые решения, вытекающие из контракта и прецедента

- **Листинг несёт полный контент.** `GET /users/me/skill-contexts` возвращает документы
  вместе с `content` (design-brief, строки 69–71). Значит превью и редактор берут данные
  из уже загруженного листинга — отдельный `GET item` для UI не нужен. Item-эндпоинт
  оставляем backend'у, в API-слой T2 не тянем (лишний, не используется).
- **Пессимистичные мутации** (`conventions/frontend.md` § Optimistic vs пессимистичные):
  PUT и DELETE ждут ответ сервера, затем `invalidateQueries` по ключу листинга. Дефолт
  проекта; правки контекста редкие — оптимистичность не нужна.
- **Серверные данные — только TanStack Query**, хуки живут в `shared/api/skill-context.ts`
  рядом с API-функциями и DTO (`conventions/frontend.md` § Ось состояния). Компоненты
  зовут хуки, не API-функции.
- **Markdown-превью — через `shared/ui/MarkdownRenderer`** (обёртка Streamdown), не собственный
  мини-рендер из мокапа (тот — только для статичного HTML-референса).
- **Security-ошибка PUT переиспользует** `isSecurityViolation` + `SECURITY_VIOLATION_MESSAGE`
  (`shared/lib/security-error.ts`) — тот же путь, что «Свои инструкции» (design-brief § UI:
  «сообщение как у Своих инструкций»).
- **Токены и темизация** — только CSS-переменные/Tailwind-утилиты, хардкод hex запрещён
  (`conventions/frontend.md` § Дизайн-токены). Мокап даёт соответствие визуала классам
  токенов (`--card`, `--muted`, `--secondary`, `--destructive-warm`, моно-шрифт для имён).

## Фазы

### T2.1: API-слой skill-context (типы, функции, хуки, query key)

**Цель:** дать компонентам типизованный доступ к CRUD `/users/me/skill-contexts` через
TanStack Query, повторяя структуру `shared/api/user-memory.ts`.

**Изменения:**
- `frontend/src/shared/api/skill-context.ts` (новый) — DTO-типы по контракту:
  `SkillContextDocument` (`key`, `description`, `content`, `created_at`, `updated_at`),
  `SkillGroup` (`skill_name`, `in_library`, `documents`), `SkillContextsResponse`
  (`{ skills: SkillGroup[] }` — **не** `ListResponse`, конверт-пагинации у ресурса нет,
  design-brief строка 65). API-функции: `getSkillContexts()` (GET листинг),
  `updateSkillContext(skillName, key, { description, content })` (PUT, возвращает документ),
  `deleteSkillContext(skillName, key)` (DELETE). Хуки: `useSkillContexts()` (query),
  `useUpdateSkillContext()` и `useDeleteSkillContext()` (мутации, `onSuccess` →
  `invalidateQueries` по ключу листинга). `skill_name` и `key` в пути —
  `encodeURIComponent` (как `deleteMemory`).
- `frontend/src/shared/api/query-keys.ts` — добавить ключ `skillContexts: ["skill-contexts"] as const`
  (внутритрековый общий файл, закреплён за T2 — design-brief строка 114). Инлайн-литералов
  ключа в хуках нет (`conventions/frontend.md` § Фабрика query keys).

**Verification:**
- `make check-fe` проходит (ESLint + Prettier + tsc).
- Типы DTO дословно соответствуют форме тел из design-brief (§ REST API, строки 67–74):
  snake_case, `content` в листинге присутствует, конверта `items/total/...` нет.

### T2.2: Секция «Контекст скиллов» — чтение и отображение

**Цель:** отрисовать секцию по мокапу в read-only режиме (группы по скиллу, бейдж
«скилла нет в библиотеке», пустое состояние, счётчик, раскрытие документа в Markdown-превью)
и встроить её в `/settings` между «Памятью агента» и MCP.

**Изменения:**
- `frontend/src/pages/user-settings/ui/SkillContextSection.tsx` (новый) — корневой компонент:
  зовёт `useSkillContexts()`, состояния загрузки / пустоты / данных. Пустое состояние —
  текст из design-brief § UI: «Пока пусто. Скиллы будут сохранять сюда ваши профили и
  предпочтения по ходу работы». Заголовок «Контекст скиллов», подпись-hint и счётчик —
  по мокапу (строки 223–234). Группа: имя скилла моноширинным; бейдж-warn при
  `in_library === false`. Документ: строка `key` + `description`, клик раскрывает
  `doc-body` с `<MarkdownRenderer>{content}</MarkdownRenderer>` в скроллируемом контейнере
  (`max-height`, `overflow-y`), `aria-expanded` на строке-кнопке. Декомпозиция на
  под-компоненты (группа / документ) — на усмотрение implementer'а; держать в том же слайсе
  `pages/user-settings/ui`, тесты co-located.
- `frontend/src/pages/user-settings/ui/SettingsPage.tsx` — добавить `<section class card>` с
  `<SkillContextSection />` между `AgentMemorySection` и `MCPServersSection` (внутритрековый
  общий файл, закреплён за T2 — design-brief строка 114).

**Verification:**
- `make check-fe` проходит.
- При непустом листинге: группировка по скиллу, внутри — документы (key + description),
  раскрытие даёт отрендеренный Markdown; при `in_library=false` виден бейдж «скилла нет в
  библиотеке» (критерий приёмки tasklist строка 541).
- Пустой листинг → текст пустого состояния из design-brief.
- Визуал совпадает с мокапом на светлой и тёмной теме; хардкода hex нет
  (`conventions/frontend.md` § Дизайн-токены).

### T2.3: Правка (raw Markdown → PUT) и удаление документа

**Цель:** добавить в раскрытый документ действия «Править» (сырой Markdown в textarea →
«Сохранить»/«Отмена») и «Удалить», с обработкой security-checkpoint как у «Своих инструкций».

**Изменения:**
- `frontend/src/pages/user-settings/ui/SkillContextSection.tsx` (и/или его под-компонент
  документа) — режим редактирования: «Править» переключает превью на `<textarea>` с сырым
  `content`; «Сохранить» зовёт `useUpdateSkillContext()` (PUT `{ description, content }` —
  `description` сохраняется из текущего документа, меняется `content`), при успехе —
  обратно в превью; «Отмена» откатывает без запроса. Кнопка «Удалить» зовёт
  `useDeleteSkillContext()`. Кнопки — `shared/ui/button` (варианты `default`/`ghost`,
  `destructive` для удаления — по прецеденту `AgentMemorySection` и палитре мокапа).
  При 422 показать `SECURITY_VIOLATION_MESSAGE` через `isSecurityViolation(error)`
  (design-brief § UI; прецедент `CustomInstructionsSection`).

**Verification:**
- `make check-fe` проходит.
- «Править» открывает сырой Markdown; «Сохранить» шлёт PUT на
  `/users/me/skill-contexts/{skill}/{key}` с телом `{ description, content }` и по успеху
  рендерит обновлённое превью; «Отмена» возвращает исходное без запроса.
- 422 от PUT → сообщение об отклонении безопасностью (то же, что «Свои инструкции»).
- «Удалить» шлёт DELETE и обновляет листинг (критерий приёмки tasklist строка 541).

## Cross-cutting

Проверить после всех фаз трека:
- Секция `/settings` целиком соответствует мокапу: группировка по скиллу, Markdown-превью
  (скролл при длинном контенте), правка raw, удаление, бейдж «скилла нет в библиотеке»,
  пустое состояние (критерий приёмки design-brief § UI / tasklist строка 541).
- Данные группы с `in_library=false` отображаются и редактируются наравне с остальными —
  UI не блокирует действия по отсутствию скилла (design-brief строка 94; критерий tasklist 542
  в части «данные переживают удаление скилла» — фронтовая половина: группа не исчезает).
- Публичный API слайса не расширяется: наружу по-прежнему экспортируется только
  `SettingsPage` (`pages/user-settings/index.ts`); секция — внутренний компонент слайса
  (`conventions/frontend.md` § Публичные API слайсов).
- A11y из мокапа сохранён: строка документа — `<button>` с `aria-expanded`, textarea с
  `aria-label`, `focus-visible` через токен `--ring`.
- Автоматические компонентные тесты трека пишет отдельный `test-author` в фазе TEST (из
  design-brief), co-located рядом с компонентами по образцу `AgentMemorySection.test.tsx`
  (MSW + `renderWithProviders`). Implementer их не создаёт; verification фаз опирается на
  `make check-fe` и критерии приёмки. Ручная проверка UI-кейсов против живого backend —
  в INTEGRATION_TEST после барьера (design-brief строка 118).

## Open Questions

Нет открытых вопросов.
