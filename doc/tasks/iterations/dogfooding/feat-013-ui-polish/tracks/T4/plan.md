# Implementation Plan: feat-013 / трек T4 — Состояния списков, страниц и роутинг

## Контекст

Трек T4 переводит весь «не-контент» продукта — загрузки, per-query ошибки, empty-state'ы и промах по URL — на фундамент, который сдал T1. Работы много не по сложности, а по ширине: одни и те же четыре формы (`Skeleton`-группа, `LoadingState`, `ErrorCard`, `StateScreen`) раскатываются по спискам, панелям и страницам, а роутер получает catch-all 404 и теряет инлайн-вёрстку заглушки артефактов. Собственной механики трек почти не вводит: единственная новая сущность — слайс `pages/not-found`.

Источники:

- Design-brief: [design-brief.md](../../design-brief.md) — блоки 3 (loading), 4 (error per-query), 6 (empty-states), 7 (catch-all 404), 2 § «Заодно» (локализация и типографика попутно), `## Партиция треков` (границы T4, закрытый список файлов, DoD T1 как контракт волны 2).
- Tasklist: [tasklist-dogfooding.md § feat-013](../../../../../tasklist-dogfooding.md) — пункты «Loading + per-query error-состояния», «Empty-state Сферы знаний», «Empty-state артефактов», «Catch-all 404-экран».
- Мокап (основной визуальный референс): [mockups/ui-polish.html](../../mockups/ui-polish.html) — секция 2 (скелетоны 546–581, спиннер-блок 583–599, карточка ошибки 601–628, полноэкранный error 630–657), секция 5 (сфера 768–795, артефакты 797–830), секция 6 (404, 834–889). Значения ниже взяты оттуда.
- Контракт волны 2: [tracks/T1/summary.md](../T1/summary.md) § «T1.4: публичный API» — сигнатуры `StateScreen`/`LoadingState`/`ErrorCard`/`Skeleton`, утверждённые ширины сцен, готовые рецепты скелетонов.
- Конвенции: [conventions.md](../../../../../../tech/conventions.md) (ядро) + [conventions/frontend.md](../../../../../../tech/conventions/frontend.md) § «Раскладка по слоям», § «Публичные API слайсов», § «Ось состояния», § «Фабрика query keys», § «Дизайн-токены»; [design-system.md](../../../../../../tech/design-system.md) § Error UX.

**Границы трека (закрытый список файлов).** T4 правит только: `app/router.tsx`; `app/components/{ErrorBoundary,ProjectList,NewChatModal,ProjectActions,ProjectCard,CreateProjectModal}.tsx`; `app/layouts/ProjectLayout.tsx`; `pages/project-chats/**`; `pages/artifacts/**`; `pages/artifact/ui/ArtifactView.tsx`; `pages/sphere/**`; `pages/security/ui/{SecurityEvents,SecurityRouteGuard,SecurityAlerts,SecurityRules,RuleForm}.tsx`; `pages/user-settings/ui/{SkillContextSection,AgentMemorySection}.tsx`; `pages/welcome/**`; `features/mcp-servers/ui/MCPServersSection.tsx`; `pages/not-found/**` (новый слайс). Параллельно в ветке идут T2 (`pages/chat/**`), T3 (`features/model-selector/**`, `pages/project-settings/**`), T6 (`features/auth/**`, `shared/ui/{AuthLayout,ProviderButton}.tsx`) — их файлы не трогаем даже одной строкой. Работа вне списка → строка в `## Follow-ups` summary + эскалация оркестратору.

**Тестовый скоуп = co-located тесты файлов трека** (правило партиции). Новых тестов трек не пишет — их пишет `test-author` отдельно. Но существующие тесты прибиты к строкам, которые трек меняет по прямому требованию брифа, и починка этих ассертов — часть фазы, а не отдельная работа. Полный список задетых тестов — в «Проверенных фактах» ниже; конкретика — в каждой фазе.

### Проверенные факты по коду (собрано по файлам скоупа, не по брифу)

**Что уже готово от T1** (`shared/ui/StateScreen.tsx`, `shared/ui/skeleton.tsx`, закоммичено `a46c804`):

- `StateScreen({ scene?, alt?, title?, description, action?, illustrationClassName?, className? })` — базовая геометрия `flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center`, `flex-1` перекрывается `className` потребителя (в не-flex родителе нужен `h-full`). `scene`/`alt` типизированы парой.
- `LoadingState({ label = "Загрузка…", className? })` — `Loader2` в `animate-spin` + подпись; растяжка по месту задаётся `className`.
- `ErrorCard({ message, onRetry?, retryLabel = "Повторить", className? })` — канонная карточка `border-destructive/30 bg-destructive/10 px-4 py-3 text-sm`, строкой «сообщение — действие»; без `onRetry` кнопка не рисуется.
- `Skeleton` — `data-slot="skeleton"`, `animate-pulse rounded-md bg-muted` **на каждой плашке**; группу вторым пульсом не оборачиваем.
- Ширины сцен (брать буквально): `error-state` 280px, `artifacts-select` 300px, `not-found` 360px, `empty-sphere` 440px. Сцены `not-found` и `artifacts-select` уже в `Scene` и в карте `shared/assets/illustrations/index.ts` (проверено), `make build-fe` их резолвит.
- Рецепты скелетонов «карточка чата» и «строка артефакта» — в summary T1 и в JSDoc `StateScreen.tsx`, пиксель в пиксель из мокапа. Брать как есть.
- **Явное решение T1:** компактные состояния списков собираются из `Skeleton` + `ErrorCard` напрямую; `StateScreen` в списках не используется — его геометрия рассчитана на полноэкранную и панельную формы.

**Инвентаризация состояний в файлах трека** (что именно и где меняется):

| Файл | Сейчас | Класс по брифу |
|------|--------|----------------|
| `app/router.tsx:23-27` | `LoadingFallback` — `<p>Загрузка...</p>` | панельная загрузка |
| `app/router.tsx:53-60` | инлайн-`div` «Выберите артефакт из списка» | empty-state 6.2 |
| `app/router.tsx` | catch-all отсутствует | блок 7 |
| `app/components/ProjectList.tsx:7-27` | `Loading...` / `text-destructive` строка / `No projects yet` | список |
| `app/components/NewChatModal.tsx:52-59` | `Загрузка проектов…` / `text-destructive` строка | список (в модалке) |
| `pages/project-chats/ui/ChatList.tsx:85-90` | `Загрузка чатов...` / `text-destructive` строка | список |
| `pages/artifacts/ui/ArtifactList.tsx:37-44` | `Загрузка…` / `text-destructive` строка | список |
| `pages/sphere/ui/SphereView.tsx:16-30` | `Loading sphere...` / `Failed to load sphere.` | панель |
| `pages/sphere/ui/SphereViewer.tsx:42-54` | empty-state `max-w-[280px]`, `py-8`, без центрирования | empty-state 6.1 |
| `pages/artifact/ui/ArtifactView.tsx:17-31` | `Загрузка артефакта…` / `text-destructive` строка | панель |
| `app/layouts/ProjectLayout.tsx:14` | `projectName = isLoading ? "Loading..." : …` | панельная загрузка |
| `pages/security/ui/SecurityRouteGuard.tsx:27-33` | `<p>Загрузка...</p>` | панельная загрузка |
| `pages/security/ui/SecurityEvents.tsx:39-45,54-57` | карточка ошибки без retry / `Загрузка события...` | список (таблица) |
| `pages/security/ui/SecurityAlerts.tsx:65-71,87-90` | то же / `Загрузка алертов...` | список (таблица) |
| `pages/security/ui/SecurityRules.tsx:111-117,140-143` | то же / `Загрузка правил...` | список (таблица) |
| `pages/security/ui/RuleForm.tsx:468` | `Сохранение...` | типографика |
| `pages/user-settings/ui/SkillContextSection.tsx:187-193` | `<p>Загрузка контекста скиллов…</p>` | панельная загрузка |
| `pages/user-settings/ui/AgentMemorySection.tsx:19-21` | `<p>Загрузка памяти…</p>` | панельная загрузка |
| `features/mcp-servers/ui/MCPServersSection.tsx:201-203` | `<p>Загрузка…</p>` | панельная загрузка |
| `app/components/ErrorBoundary.tsx:24-51` | своя вёрстка: sans-заголовок, сырой `<button>`, сцена `h-48` | блок 2 |
| `app/components/ProjectActions.tsx:108,118,128-131,152,162,173-177,184,191` | весь копирайт английский | блок 2 «Заодно» |
| `app/components/CreateProjectModal.tsx:55,58,76` | `New Project` / `Project name` / `Create` | блок 2 «Заодно» |
| `pages/welcome/ui/WelcomePage.tsx:74` | `alt="Welcome to LearnFlowAI"` | блок 2 «Заодно» |
| `pages/artifacts/ui/ArtifactList.tsx:50` | `alt="No artifacts yet"` | блок 2 «Заодно» |
| `pages/sphere/ui/SphereViewer.tsx:46` | `alt="Knowledge sphere is empty"` | блок 2 «Заодно» |

Многоточия `...` вместо `…` — `router.tsx:25`, `ChatList.tsx:64,86`, `SecurityRouteGuard.tsx:30`, `SecurityEvents.tsx:56`, `SecurityAlerts.tsx:89`, `SecurityRules.tsx:142,259`, `RuleForm.tsx:468`. Всё это переписывается в фазе, которая и так трогает строку.

**Существующие тесты, прибитые к меняемым строкам** (все — co-located тесты файлов трека, чинятся своей фазой):

- `app/router.test.tsx:142` — `GUARD_LOADING = "Загрузка..."`; **и главное** — кейс «has no /security route at all in a SIEM-off build» ассертит `expect(container).toBeEmptyDOMElement()`. Catch-all это поведение отменяет намеренно (бриф блок 7: «это же закрывает `/security` при выключенном SIEM-флаге»), ассерт переписывается.
- `pages/project-chats/ui/ChatList.test.tsx:22` — константа плейсхолдера с `...`; `:233` — «Не удалось загрузить чаты.» (строка сохраняется).
- `pages/artifacts/ui/ArtifactList.test.tsx:85` — «Ошибка загрузки артефактов.».
- `pages/sphere/ui/SphereView.test.tsx:57,70` — `/Сфера знаний пуста/` (сохраняется) и «Failed to load sphere.».
- `pages/security/ui/SecurityEvents.test.tsx:53,74`, `SecurityRules.test.tsx:53,74`, `SecurityRouteGuard.test.tsx:85`.
- `app/components/NewChatModal.test.tsx:113,133`, `pages/user-settings/ui/{SkillContextSection,AgentMemorySection}.test.tsx`, `features/mcp-servers/ui/MCPServersSection.test.tsx:54` — строки подписей сохраняются, ассерты остаются зелёными без правок (проверить, а не править вслепую).

**Роутер, слайс 404 и eslint-boundaries** (проверено по `frontend/eslint.config.mjs`, не по памяти):

- Правило одно — `boundaries/dependencies` c `default: "disallow"`. Из `app` разрешено: `app → app`, `app → shared|stores`, и `app → pages|features` **только через `internalPath: "index.{ts,tsx}"`**.
- Элемент `pages` объявлен паттерном `src/pages/*` (`mode: "folder"`), то есть **новая директория подхватывается автоматически** — регистрировать слайс в конфиге не нужно.
- Отсюда раскладка 404: `src/pages/not-found/ui/NotFoundPage.tsx` + `src/pages/not-found/index.ts` (`export { NotFoundPage } from "./ui/NotFoundPage";`), роутер импортирует `import { NotFoundPage } from "@/pages/not-found";`. Импорт из `@/pages/not-found/ui/NotFoundPage` правило нарушит — так не делать.
- Заглушка артефактов кладётся внутрь существующего слайса (`pages/artifacts/ui/…`) и экспортируется из его `index.ts` — `pages/artifacts/**` целиком принадлежит T4, новые файлы там границ не задевают.
- `Button` — обёртка над Base UI `ButtonPrimitive`, принимает `render`-проп (в репозитории уже так: `DropdownMenuTrigger render={<Button …/>}`). CTA 404 = `<Button render={<Link to="/" />}>На главную</Button>`; если типы Base UI заартачатся — фолбэк `<Link to="/" className={buttonVariants()}>` (`buttonVariants` экспортируется из `shared/ui/button.tsx`).

**Прочее:**

- Все затронутые data-хуки — обёртки `useQuery` (`useProjects`, `useChats`, `useArtifacts`, `useArtifact`, `useSphere`, `useEvents`, `useAlerts`, `useRules`), поэтому `refetch` берётся из результата хука. Инлайн-ключей и прямых вызовов `queryClient` для повтора не заводить (`conventions/frontend.md` § Фабрика query keys).
- `ArtifactsPage` рисует вьюер как `<div className="flex min-w-0 flex-1 overflow-hidden"><Outlet/></div>` — flex-контейнер, поэтому `flex-1` у `StateScreen` там работает и заглушка встаёт по центру без дополнительных классов. Это и есть причина бага 6.2: инлайн-`div` в роутере не был flex-item с `flex-1`.
- Пустая сфера живёт **внутри `ScrollArea`** (`SphereViewer.tsx:37`), а не в обычном `overflow-auto`: `flex-1` там не сработает, растяжка задаётся `h-full` (viewport Base UI — `size-full`).
- Проверка «нет hex/rgba в `.tsx`» (design-system.md § Границы) остаётся в силе: все цвета — утилиты токенов.

**Стык с feat-008.** Правка `router.tsx` в этом треке — одна строка catch-all плюс замена инлайн-заглушки на импорт компонента; структурную перестройку входа делает feat-008, конфликт merge разруливает мержащийся вторым. Ничего сверх этого в `router.tsx` не менять.

## Фазы

### T4.1: Роутинг — catch-all 404, слайс `pages/not-found`, заглушка артефактов, Suspense-fallback

**Цель:** закрыть блок 7 и блок 6.2 — любой нелегитимный URL показывает брендовый 404 внутри `AppLayout` (сайдбар на месте), а заглушка «выберите артефакт» уезжает из роутера в компонент и встаёт по центру панели.

**Изменения:**

- `frontend/src/pages/not-found/ui/NotFoundPage.tsx` (новый) — `StateScreen` в полноэкранной форме, значения из мокапа (882–887):
  - `scene="not-found"`, `alt="Иллюстрация: страница не найдена"`, `illustrationClassName="max-w-[360px]"`;
  - `title="Страница не найдена"`;
  - `description="Такой страницы нет или она переехала. Вернитесь на главную и продолжите оттуда."`;
  - `action` — кнопка **primary** (утверждено на финальном ревью мокапа, не outline) со ссылкой на `/`: `<Button render={<Link to="/" />}>На главную</Button>`.
  - Компонент презентационный: ни хуков данных, ни логирования.
- `frontend/src/pages/not-found/index.ts` (новый) — `export { NotFoundPage } from "./ui/NotFoundPage";`. Публичный API слайса, единственная точка входа для роутера.
- `frontend/src/pages/artifacts/ui/NoArtifactSelected.tsx` (новый) — `StateScreen` без заголовка (мокап 824–827): `scene="artifacts-select"`, `alt="Иллюстрация: выберите артефакт"`, `illustrationClassName="max-w-[300px]"`, `description="Выберите артефакт из списка слева, чтобы посмотреть его."`.
- `frontend/src/pages/artifacts/index.ts` — добавить экспорт нового компонента рядом с `ArtifactList`/`ArtifactsPage`.
- `frontend/src/app/router.tsx` — ровно три правки:
  1. `LoadingFallback` заменяется на `<LoadingState className="h-full" />` (дефолтная подпись «Загрузка…» с типографским многоточием); локальный компонент-обёртка удаляется, если после замены не нужен.
  2. индекс-роут артефактов: инлайн-`div` → `<NoArtifactSelected />`;
  3. последним ребёнком роута `AppLayout` — `<Route path="*" element={<NotFoundPage />} />`. Не редирект, не `Navigate`; вне `AppLayout` не выносить — весь смысл в том, что сайдбар остаётся.
- `frontend/src/app/router.test.tsx` — починка ассерта, который catch-all отменяет намеренно: кейс «has no /security route at all in a SIEM-off build» больше не может ждать пустой DOM. Переформулировать под новое поведение: в SIEM-off сборке `/security` рендерит 404-экран (и **не** рендерит страницу Security / состояние гарда). Комментарий над кейсом переписать — сейчас он объясняет ровно ту механику («nothing matches, so not even the app layout renders»), которая перестала быть правдой; оставить его значит соврать следующему читателю. Остальные кейсы файла не трогать.

**Verification:**

- `make check-fe` и `make test-fe` зелёные; `make build-fe` проходит (сцена `not-found` резолвится в бандл).
- Ручная сверка на `make dev-fe`, обе темы: `/чепуха` → сайдбар виден, по центру рабочей зоны сцена `not-found` шириной 360px, serif-заголовок «Страница не найдена», подпись, primary-кнопка «На главную»; клик уводит на `/` (переход клиентский, без перезагрузки).
- `/security` при `SIEM_ENABLED=false` даёт тот же 404 (а не пустой экран). При `SIEM_ENABLED=true` и не-админе поведение прежнее — редирект гарда на `/`; несимметрия намеренная (бриф блок 7), к единому виду не приводить.
- Вкладка «Артефакты» без выбранного артефакта: сцена `artifacts-select` 300px по центру правой панели по обеим осям, подпись под ней; при выборе артефакта заглушка сменяется вьюером.
- Suspense-загрузка Security-страницы показывает центрированный спиннер с подписью «Загрузка…» (типографское многоточие).
- `git diff` роутера содержит ровно три смысловые правки — стык с feat-008 не расширен.

### T4.2: Списки — скелетоны загрузки и карточка ошибки с «Повторить»

**Цель:** закрыть блоки 3 и 4 в их «списочной» половине: четыре списка получают скелетоны по форме будущих строк и компактную карточку ошибки, дающую путь восстановления помимо F5.

**Изменения:**

- `frontend/src/pages/project-chats/ui/ChatList.tsx`:
  - `useChats(id)` → забрать `refetch`;
  - `isLoading` → группа из **двух** скелетонов карточки чата по рецепту T1 (мокап 560–573: `h-3.5 w-[46%]`, `mt-[7px] h-2.5 w-[68%]`, чип `h-4 w-16 rounded-full` + `mt-[3px] h-2.5 w-[34px]`; вторая карточка — те же плашки с другими ширинами, `w-[58%]`/`w-[44%]`/`w-[52px]`). Контейнер группы **без** `animate-pulse` — он на плашках;
  - `isError` → `<ErrorCard message="Не удалось загрузить чаты." onRetry={() => void refetch()} />` (строка сохраняется — тест `ChatList.test.tsx:233` остаётся зелёным);
  - «Заодно»: плейсхолдер `…новый чат...` → `…новый чат…`, вместе с константой в `ChatList.test.tsx:22`.
- `frontend/src/pages/artifacts/ui/ArtifactList.tsx`:
  - `useArtifacts(id)` → забрать `refetch`;
  - `isLoading` → две-три строки скелетона артефакта по рецепту T1 (`h-9 w-9 rounded-[calc(var(--radius)*0.8)]` + `h-3 w-[62%]` + `mt-1.5 h-2.5 w-[32%]`);
  - `isError` → `ErrorCard` с текстом «Не удалось загрузить артефакты.» и `onRetry`; ассерт `ArtifactList.test.tsx:85` привести к новой строке (унификация формулировок блока 4: «Не удалось загрузить …»);
  - «Заодно»: `alt="No artifacts yet"` → «Иллюстрация: артефактов пока нет».
- `frontend/src/app/components/ProjectList.tsx`:
  - `useProjects()` → забрать `refetch`;
  - `isLoading` → три скелетона пункта проекта по форме реальной строки `ProjectCard` (`flex items-center gap-2 px-3 py-1.5`: точка `h-2 w-2 rounded-full` + полоса названия, ширины разные — напр. `w-[70%]`, `w-[52%]`, `w-[61%]`);
  - `isError` → `ErrorCard` («Не удалось загрузить проекты») с `onRetry`. Список живёт в сайдбаре шириной 252px — карточке нужен компактный вариант (`className` с меньшими отступами и переносом действия на вторую строку, если «Повторить» не влезает в строку). Проверить именно на 252px, а не на глаз в широкой панели;
  - «Заодно»: `Loading...` уходит вместе со скелетоном, `No projects yet` → «Проектов пока нет».
- `frontend/src/app/components/NewChatModal.tsx`:
  - `useProjects()` → забрать `refetch`;
  - `isLoading` → `<LoadingState label="Загрузка проектов…" className="py-2" />` (модалка не входит в четвёрку списков со скелетонами — её высота не фиксирована и геометрию сохранять нечему);
  - `isError` → `<ErrorCard message="Не удалось загрузить список проектов" onRetry={() => void refetch()} />`.
  - Обе строки сохраняются дословно — `NewChatModal.test.tsx:113,133` остаются зелёными.
  - *Решение планировщика:* модалка не перечислена в списке блока 4 поимённо, но лежит в закрытом списке T4 и несёт ровно тот же голый `text-destructive` за той же `useProjects`. Канонизация формы из блока 4 на неё распространяется; отдельного дизайн-решения тут нет.

**Verification:**

- `make check-fe` и `make test-fe` зелёные; поправлены ровно те ассерты, что перечислены выше.
- Скелетоны сверены с мокапом **по значениям**, а не на глаз: ширины/высоты плашек совпадают с рецептом T1 (он — перевод `.sk-chat`/`.sk-art` из мокапа в утилиты), пульсация одна (нет вложенного `animate-pulse`), геометрия строки совпадает с будущей реальной строкой — при подмене данных экран не «прыгает».
- Ошибка и восстановление проверены вживую (dev-tools → офлайн или MSW-500): в каждом из четырёх мест видна карточка `border-destructive/30 bg-destructive/10` с «Повторить»; клик реально шлёт запрос (Network) и при успехе список наполняется без перезагрузки страницы.
- В сайдбаре карточка ошибки не обрезана и не выталкивает скролл по горизонтали при 252px.
- Англоязычных строк в четырёх файлах не осталось; многоточия типографские.

### T4.3: Сфера и артефакт — панельные загрузка/ошибка и empty-state сферы

**Цель:** закрыть блоки 3 и 4 в «панельной» половине для сферы и артефакта и блок 6.1 — пустая сфера центрируется по высоте панели и получает крупную сцену с CTA.

**Изменения:**

- `frontend/src/pages/sphere/ui/SphereView.tsx`:
  - `useSphere(id)` → забрать `refetch`;
  - `isLoading` → `<LoadingState className="h-full" label="Загрузка сферы…" />` (было англоязычное `Loading sphere...`);
  - `isError` → `StateScreen` полноэкранной формы по мокапу 649–654: `scene="error-state"`, `alt="Иллюстрация: ошибка"`, `illustrationClassName="max-w-[280px]"`, `title="Не удалось загрузить сферу знаний"`, `description="Что-то пошло не так при загрузке. Проверьте соединение и попробуйте ещё раз."`, `action` — `<Button variant="outline" onClick={() => void refetch()}>Повторить</Button>`, `className="h-full"`;
  - ассерт `SphereView.test.tsx:70` («Failed to load sphere.») привести к новому заголовку.
- `frontend/src/pages/sphere/ui/SphereViewer.tsx` — ветка пустого содержимого переезжает на `StateScreen` (мокап 790–794):
  - `scene="empty-sphere"`, `illustrationClassName="max-w-[440px]"` (утверждённый канон; 280px — то, что чиним), `alt="Иллюстрация: пустая сфера знаний"` (было англоязычное);
  - `description="Сфера знаний пуста — здесь будет накапливаться память проекта."` — регэксп `/Сфера знаний пуста/` в `SphereView.test.tsx:57` продолжает совпадать;
  - `action` — кнопка «Редактировать» с иконкой `Pencil`, стилистически та же, что в шапке вьюера (`variant="outline" size="sm"` + акцентные классы `border-ring/60 text-ring`), вызывает тот же `onEdit`;
  - растяжка — `className="h-full"`, **не** `flex-1`: блок лежит внутри `ScrollArea`, viewport которой `size-full`, и `flex-1` там ни на что не влияет. Итог — вертикальный центр в высоте панели, а не прижатый верх.
- `frontend/src/pages/artifact/ui/ArtifactView.tsx`:
  - `useArtifact(id, aid)` → забрать `refetch`;
  - `isLoading` → `<LoadingState className="h-full" label="Загрузка артефакта…" />`;
  - `isError` → `StateScreen` той же формы, `title="Не удалось загрузить артефакт"`, та же подпись и «Повторить», `className="h-full"` (родитель — flex-контейнер `ArtifactsPage`, но `h-full` безопаснее и совпадает с соседями).
  - Остальной файл (диспетчер по типам, вьюеры, шапка) не трогать.

**Verification:**

- `make check-fe` и `make test-fe` зелёные; правлен ровно один ассерт (`SphereView.test.tsx:70`).
- Пустая сфера на `make dev-fe` (проект без содержимого сферы), обе темы: сцена ~440px по ширине, блок отцентрирован по вертикали в высоте панели (сверху и снизу свободного места поровну — сверять по окну, а не по скриншоту в одной высоте), под сценой подпись и кнопка «Редактировать», клик открывает редактор.
- Ошибка сферы и ошибка артефакта (MSW-500 / офлайн): сцена `error-state` 280px, serif-заголовок, подпись, «Повторить»; клик перезапрашивает и восстанавливает экран.
- Загрузки: спиннер + подпись по центру панели, без иллюстрации (бриф блок 3 — сцена в переходном состоянии лишняя).
- Англоязычных строк и `alt` в `pages/sphere/**` и `ArtifactView.tsx` не осталось.

### T4.4: SIEM-экраны — скелетоны таблиц, ошибки с повтором, гард

**Цель:** довести три таблицы SIEM и гард маршрута до общей системы состояний: карточка ошибки получает «Повторить», плоские «Загрузка …» уступают скелетонам таблицы, гард — общему спиннер-блоку.

**Изменения:**

- `frontend/src/pages/security/ui/SecurityRouteGuard.tsx` — ветка `isLoading` → `<LoadingState className="h-full" />` (дефолтная подпись «Загрузка…»). Логика гарда (`enabled: !!token`, `getIsAdminFromAccessToken`, `Navigate` на `/`) не меняется — редирект остаётся редиректом, 404 его не заменяет (бриф блок 7).
- `frontend/src/pages/security/ui/SecurityEvents.tsx`, `SecurityAlerts.tsx`, `SecurityRules.tsx` — три однотипные правки:
  - забрать `refetch` из `useEvents`/`useAlerts`/`useRules`;
  - ветка `error` → `<ErrorCard message={…} onRetry={() => void refetch()} />`; текст унифицируется под формулировку блока 4: «Не удалось загрузить события: {детали}» / «…алерты…» / «…правила…», детали по-прежнему из `getApiErrorMessage(error)`. Ассерты `SecurityEvents.test.tsx:74` и `SecurityRules.test.tsx:74` (`/Ошибка загрузки …/`) привести к новой формулировке;
  - ветка `isLoading` → скелетон таблицы вместо центрированной строки: сохранить контейнер `rounded-lg border border-border bg-card` и нарисовать в нём 5 строк-заглушек (`flex items-center gap-4 px-4 py-3` + `Skeleton`-полосы разной ширины, разделители `divide-y divide-border` как у настоящей таблицы). Геометрия экрана при подмене данными не должна прыгать — это и есть критерий формы;
  - ассерты `SecurityEvents.test.tsx:53` и `SecurityRules.test.tsx:53` («Загрузка события...», «Загрузка правил...») переписать на проверку скелетона (например, по `[data-slot="skeleton"]` — атрибут даёт сам примитив T1), а не на исчезнувшую строку;
  - `SecurityRouteGuard.test.tsx:85` и константа `GUARD_LOADING` в `app/router.test.tsx:142` — привести к «Загрузка…» (типографское многоточие).
  - *Решение планировщика:* бриф поимённо называет в списочной группе только `SecurityEvents`, но алерты и правила — те же таблицы на том же экране, в трёх вкладках одного `SecurityPage`. Разное поведение загрузки между вкладками было бы новым разнобоем вместо снятого. Общий компонент под скелетон **не заводится**: `pages/security/ui/` отдан треку поимённым списком файлов, а не `**`, и новый файл там вышел бы за закрытый список; три инлайновых блока по 6 строк дешевле эскалации.
- `frontend/src/pages/security/ui/RuleForm.tsx` — только типографика: «Сохранение...» → «Сохранение…». Карточку ошибки формы (`RuleForm.tsx:180`) не трогаем: она уже в канонной форме, а ошибки мутаций/валидации бриф в этом блоке не переделывает.

**Verification:**

- `make check-fe` и `make test-fe` зелёные; правлены ровно перечисленные ассерты.
- На `make dev-fe` с админской сессией (`make grant-admin USER=…`), обе темы: три вкладки SIEM показывают одинаковый скелетон таблицы при загрузке; при MSW-500/офлайне — карточку ошибки с «Повторить», клик перезапрашивает вкладку и восстанавливает таблицу.
- Гард: на входе в `/security` до ответа `/auth/me` виден центрированный спиннер с подписью «Загрузка…»; не-админ по-прежнему улетает на `/`.
- Плоских «Загрузка …» в файлах SIEM не осталось, многоточия типографские.

### T4.5: `ErrorBoundary` на `StateScreen`, остаточные панельные загрузки и локализация

**Цель:** закрыть блок 2 в части трека — унифицировать брендовый `ErrorBoundary`, перевести оставшиеся панельные загрузки на `LoadingState` и вычистить англоязычный копирайт в проектных модалках и `alt`-подписях.

**Изменения:**

- `frontend/src/app/components/ErrorBoundary.tsx` — `render()` переезжает на `StateScreen` (мокап 648–654, колонка «станет»):
  - `scene="error-state"`, `alt="Иллюстрация: ошибка"`, `illustrationClassName="max-w-[280px]"` (было `h-48 w-auto`);
  - `title="Что-то пошло не так"` — теперь serif-заголовком компонента, а не sans-`h1`;
  - `description="Произошла непредвиденная ошибка. Попробуйте обновить страницу."`;
  - `action` — `<Button variant="outline" onClick={() => window.location.reload()}>Обновить страницу</Button>` вместо сырого `<button>`;
  - `className="h-screen bg-background text-foreground"` — компонент рисуется вне обычного layout'а, фон и цвет текста задать явно;
  - **`componentDidCatch` → `logger.error("render error", error, errorInfo)` сохраняется дословно** (прямое требование брифа: унификация визуальная, логирование не трогаем). `getDerivedStateFromError` и структура класса не меняются.
- `frontend/src/app/layouts/ProjectLayout.tsx` — вместо `projectName = isLoading ? "Loading..." : …` в заголовке рисовать `Skeleton` по форме названия (`h-4 w-28`), а после загрузки — само название. Спиннер в строке заголовка неуместен, а скелетон сохраняет геометрию шапки — тот же принцип, что в списках.
- `frontend/src/pages/user-settings/ui/SkillContextSection.tsx` — `isLoading` → `<LoadingState label="Загрузка контекста скиллов…" className="py-6" />` (строка сохраняется, `SkillContextSection.test.tsx:63` остаётся зелёным).
- `frontend/src/pages/user-settings/ui/AgentMemorySection.tsx` — то же с `label="Загрузка памяти…"` (`AgentMemorySection.test.tsx:48` — зелёный).
- `frontend/src/features/mcp-servers/ui/MCPServersSection.tsx` — то же с дефолтной подписью «Загрузка…» (`MCPServersSection.test.tsx:54` — зелёный).
- `frontend/src/app/components/ProjectActions.tsx` — локализация всего копирайта. Эталон формулировок — уже локализованный сосед `features/chat-actions/ui/ChatActions.tsx` (файл чужой, только читаем): пункты меню «Переименовать» / «Удалить»; диалог переименования — заголовок «Переименовать проект», описание «Введите новое название проекта.», кнопки «Отмена» / «Сохранить»; диалог удаления — заголовок «Удалить проект», описание в форме «Удалить «{projectName}»? …» с честным перечислением последствий и «Это действие нельзя отменить.», кнопки «Отмена» / «Удалить». Логика мутаций, `logger.error`-сообщения (это события лога, не UI) и разметка не меняются.
- `frontend/src/app/components/CreateProjectModal.tsx` — «New Project» → «Новый проект», `placeholder="Project name"` → «Название проекта», кнопка «Create» → «Создать».
- `frontend/src/pages/welcome/ui/WelcomePage.tsx` — `alt="Welcome to LearnFlowAI"` → русская подпись сцены (по образцу остальных: «Иллюстрация: добро пожаловать в LearnFlow AI»). Больше в файле ничего.
- `frontend/src/app/components/ProjectCard.tsx` — правок не требуется (проверено: строк UI нет, комментарии английские — это код, не копирайт). Файл остаётся в скоупе как владение, не как работа.

**Verification:**

- `make check-fe` и `make test-fe` зелёные; ассерты трёх секций-настроек и MCP не потребовали правок (если потребовали — значит подпись разъехалась, вернуть дословную).
- `ErrorBoundary` проверить живым бросанием ошибки в дочернем компоненте (временный `throw` в dev, откатить после проверки): сцена 280px, **serif**-заголовок, подпись, кнопка «Обновить страницу» в стиле продукта; в консоли — запись `logger.error("render error", …)`, то есть логирование не потеряно.
- Шапка проекта при холодной загрузке показывает скелетон-полосу вместо слова «Loading...», ширина шапки не прыгает при появлении названия.
- Модалки проекта (создание, переименование, удаление) — целиком по-русски, формулировки совпадают по тону с диалогами чата; кавычки-ёлочки, многоточия типографские.
- Финальный греп по файлам трека: ни одного англоязычного пользовательского текста (`alt`, `title`, `placeholder`, подписи кнопок и заголовки), ни одного `...` вместо `…`.

## Cross-cutting

После всех фаз трека:

- `make check-fe`, `make build-fe`, `make test-fe` — зелёные по всему фронтенду; чужих провалов (T2/T3/T6 идут параллельно) в отчёт не приписывать, но и своих не оставлять.
- Обе темы проверены вживую на `make dev-fe` по всем затронутым экранам: списки (сайдбар, чаты, артефакты), панели (сфера, артефакт), SIEM, 404, заглушка артефактов, `ErrorBoundary`.
- Все четыре формы состояний берутся из `shared/ui/StateScreen.tsx` и `shared/ui/skeleton.tsx` — своих локальных спиннеров, своих карточек ошибки и своих плашек скелетона в файлах трека не появилось (греп на `animate-pulse`, `border-destructive/30`, `Loader2` вне импортов из `shared/ui`).
- Ни одного хардкода hex/rgba в `.tsx`; цвета — только утилиты токенов (design-system.md § Границы).
- `git status` не показывает изменений вне закрытого списка T4 — проверка изоляции перед каждым коммитом, параллельно идут три трека.
- Коммиты пофазные, по одному на фазу; в сообщении фазы, правящей `router.tsx`, отметить стык с feat-008 (одна строка catch-all).
- В summary трека обязательно зафиксировать: (1) изменившийся контракт теста `router.test.tsx` про SIEM-off `/security` — это намеренная смена наблюдаемого поведения, а не починка «упавшего теста»; (2) полный список правленных ассертов; (3) `## Follow-ups` с находками вне скоупа (см. Open Questions).

## Open Questions

1. **Англоязычные `aria-label` в `pages/security/ui/SecurityPagination.tsx` (`Previous page`, `Next page`).** Это ровно класс блока 2 «Заодно» — доступные имена контролов на английском в русском продукте, — но файл не входит ни в один трек партиции, а правило закрытого списка запрещает править неперечисленное. Дефолт плана: **не трогать**, строкой в `## Follow-ups` summary трека и эскалацией оркестратору. Нужен ответ: расширить скоуп T4 на этот файл (правка на две строки, конфликтов ни с кем нет) или оставить в follow-ups до отдельного захода. Той же проверки заслуживают соседи по `pages/security/ui/`, не попавшие в список (`SecurityPage.tsx`, `SecurityFilter.tsx`, `SeverityBadge.tsx`, `StatusBadge.tsx`) — беглый просмотр англоязычного копирайта в них не показал, но полную вычитку T4 не делал, потому что это чужие файлы.

## Резолюции оркестратора

1. **`SecurityPagination.tsx` добавлен в скоуп T4** (секция `## Партиция треков` design-brief обновлена; треки волны 2 ещё не стартовали, живых читателей у файла нет). Англоязычные `aria-label="Previous page" / "Next page"` — тот же класс блока 2 «Заодно», что и остальные строки трека, файл лежит в директории, пятью соседями которой T4 уже владеет, правка — две строки, конфликтовать не с кем. Оставить их до отдельного захода значило бы сдать предпоказную полировку, в которой скринридер на SIEM-экране продолжает говорить по-английски. Границу держим: расширение — ровно на этот файл и ровно на две подписи, остальных соседей по `pages/security/ui/` трек не трогает.

2. **Ассерт `router.test.tsx` про SIEM-off правит `test-author`, а не implementer.** План верно диагностировал, что кейс «has no /security route at all in a SIEM-off build» (`expect(container).toBeEmptyDOMElement()`) кодирует поведение, которое бриф блока 7 отменяет намеренно: после catch-all `/security` при выключенном флаге отдаёт 404 внутри `AppLayout`. Но правка ассерта имплементером — ровно то, что запрещает A6 (`testing.md` § Целостность тестов): переписать спецификацию под свою реализацию. Судить, каким должен стать ассерт, обязан независимый автор тестов, читающий контракт из брифа.

   Порядок для трека: **IMPLEMENT** реализует фазы и сдаёт прогон, в котором краснеют **только** кейсы, поимённо перечисленные в плане как ожидаемые (SIEM-off в `router.test.tsx` и те, что прибиты к дословным строкам загрузки — `GUARD_LOADING`, плейсхолдер `ChatList`, `ArtifactList`, `SphereView`, SIEM-суиты). Любой красный сверх этого списка — сигнал регрессии, повод разбираться в коде, а не в тесте; тест-файлы имплементер не открывает на запись. **TEST_AUTHORING** приводит устаревшие ассерты к новому контракту и дописывает покрытие нового поведения. Зелёный гейт трека фиксируется по итогам TEST_AUTHORING и GREEN, а не по итогам IMPLEMENT.

## Правки по plan-review (внесены оркестратором, обязательны к исполнению)

Ревью плана свежим агентом: blocker — 2, nit — 3, question — 1. Покрытие блоков 3/4/6/7 подтверждено пофайлово, включая полноту инвентаризации строк. **При расхождении этой секции с телом фаз приоритет у неё.**

1. **Тест-файлы имплементер не открывает на запись — во всех фазах, не только в T4.1.** Тело плана в четырёх фазах поручает ему «привести ассерт», «переписать комментарий над кейсом», «поправить константу плейсхолдера». Резолюция 2 запрещает это целиком: правка ассертов под свою реализацию — то, против чего написан A6 (`testing.md` § Целостность тестов). Читай все такие пункты фаз как **перечень ожидаемо красных кейсов после IMPLEMENT**, а не как задание. Ожидаемые красные: `router.test.tsx` (SIEM-off), `ArtifactList.test.tsx:85`, `ChatList.test.tsx:22` (константа плейсхолдера), `SphereView.test.tsx:70`, SIEM-суиты и `SecurityRouteGuard.test.tsx:85` (`GUARD_LOADING`). Любой красный сверх этого списка — регрессия, разбираться в коде. Ассерты приводит к новому контракту `test-author`; зелёный гейт трека фиксируется после GREEN, а не после IMPLEMENT.

2. **`SecurityRules.tsx:196,207` — ещё две англоязычные подписи, пропущенные инвентаризацией.** `aria-label="Edit rule"` и `aria-label="Delete rule"` — ровно тот класс блока 2 «Заодно», ради которого в скоуп добавлен `SecurityPagination`, причём в файле, который треку уже принадлежит. Перевести в фазе T4.4 («Редактировать правило» / «Удалить правило»). **`aria-label` добавить в финальный греп фазы T4.5** — сейчас его в перечне нет, и именно поэтому пропуск не был бы пойман проверкой.

3. **`SecurityPagination.tsx` вплести в тело плана.** Резолюция 1 добавила файл в скоуп, но границы трека, фаза T4.4 и Open Question 1 по-прежнему говорят «не трогать» — имплементер, читающий фазы, правку пропустит. Файл входит в закрытый список; две подписи (`Previous page` / `Next page`) переводятся в фазе T4.4; Open Question 1 считается закрытым.

4. **`ProjectLayout` — перевод строки, а не скелетон в шапке.** Бриф блока 2 просит здесь ровно перевод («`Loading...` в `ProjectLayout` — всё переводится»), а двухуровневый паттерн блока 3 знает только две формы: скелетоны для списков и спиннер-блок для панелей и полных экранов. Скелетон в шапке — третья форма, которой нет ни в мокапе, ни в паттерне, и она противоречит собственной классификации плана («панельная загрузка»). Ставим «Загрузка…». Если архитектор захочет скелетон — это отдельное решение, не умолчание имплементера.

5. **Скелетон SIEM-таблицы — 2–3 строки, не 5.** Бриф блока 3 задаёт число явно («2–3 мерцающих плейсхолдера»), а канона геометрии для таблицы в мокапе нет — форма и так изобретается, тем важнее держаться единственной заданной величины. Три строки.
