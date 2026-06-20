# Implementation Plan: feat-004 — Design-system integration

## Контекст

Переносим спроектированную в feat-001 дизайн-систему «Чернила / Электрик» из пакета хэндоффа в код фронтенда. Цель Фазы 4 — продукт перестаёт выглядеть generic: фирменные токены light+dark с переключателем темы, три брендовых шрифта, wordmark и Сфера-орб кодом, иллюстрации, рестайл всех существующих экранов (группа A) и новые интеракции группы B на заглушках. Бэкенд не трогаем — контракты группы B уходят в бэклог брифа.

Это не проектирование с нуля: пиксельный first-source — пакет хэндоффа, воспроизводим средствами текущей дизайн-системы (Tailwind v4 CSS-first, shadcn base-nova, CVA-варианты, lucide), а не копированием HTML.

**Источники (пути от worktree-корня):**
- Tasklist: `doc/tasks/tasklist-design-branding.md` (запись feat-004)
- Design-brief: `doc/tasks/iterations/design-branding/feat-004-design-system-integration/design-brief.md` — scope (A/B), границы, ключевые решения, трек-декомпозиция §7, архитектура верификации §8
- Test-cases: `doc/tasks/iterations/design-branding/feat-004-design-system-integration/test-cases.md` — ID кейсов (DP, L0, T1–T6, E2E)
- Хэндофф README (пиксельный first-source): `doc/tasks/iterations/design-branding/feat-001-poc/design-handoff/design_handoff_brand_electric/README.md` — токены, типографика, wordmark K5, 11 экранов, интеракции, state; рядом `*.dc.html` — эталоны гештальта для визуального ревью
- FSD-конвенции проекта: `doc/tech/conventions.md` § Frontend (раскладка по слоям, граница shadcn в `shared/ui`, ось state Query/Zustand)
- Карта экранов/маршрутов/компонентов: `doc/tech/frontend.md`

**Заземление на реальный код (сверено):**
- Стек: React 19, Vite 7, Tailwind v4 (CSS-first, `@theme` в `frontend/src/index.css`, без config), shadcn `base-nova` на Base UI, lucide, `react-router` v7 (JSX `<Routes>` в `app/router.tsx`, `<BrowserRouter>` в `App.tsx`), TanStack Query v5, Zustand v5.
- Токены: `frontend/src/index.css` — формат уже совпадает (OKLCH, light в `:root`, dark в `.dark`, `@custom-variant dark`, `@theme inline`). `--font-sans: "Geist Variable"`. **Рантайм-переключателя темы нет** (класс `.dark` определён, но никогда не вешается).
- Шрифт: установлен только `@fontsource-variable/geist`. Трёх брендовых шрифтов нет.
- `sonner` НЕ установлен, тост-инфраструктуры нет вообще (greenfield для T5).
- Сторы: `frontend/src/stores/{ui-store,stream-store}.ts`. Theme-store нет.
- Текстовый логотип «LearnFlowAI» (plain text, без компонента): `frontend/src/app/components/Sidebar.tsx:51` и `frontend/src/pages/welcome/ui/WelcomePage.tsx:5`.
- QueryClient: `frontend/src/app/providers/QueryProvider.tsx` — 4xx уже не ретраит (`shouldRetryQuery`), `onError` логирует через `logger` + `getApiErrorMessage`. Тоста на ошибку нет.
- Захардкоженные цвета: `app/components/ErrorBoundary.tsx` — целиком инлайн-стили + hex (`#666`/`#ccc`/`#fff`); `pages/security/ui/` — Tailwind-палитра `red/green/blue/yellow-50/200/500/700` в `SeverityBadge`, `StatusBadge`, `RuleForm`, `SecurityRules`, `SecurityEvents`, `SecurityAlerts`.
- `shared/lib/api-error.ts` и `logger.ts` — существуют.
- Cutout-ассеты подтверждены: `doc/.../feat-001-poc/refs/illustrations/candidates/transparent/soft-balanced/{light,dark}/` — 6 сцен × 2 темы: `welcome-hero`, `sidebar-vignette`, `empty-chats`, `empty-sphere`, `empty-artifacts`, `error-state`.

**Заземление на backend (для DP):** основной бэкенд в `backend/`. Реляционные модели/репозитории есть для User/Project/ThreadView(чат)/Artifact. **Сообщения чата и Сфера знаний — НЕ реляционные**: сообщения живут в LangGraph-checkpointer (`AsyncPostgresSaver`), сфера — в LangGraph-store (`LangGraphSphereService`, namespace `("project", id, "sphere")`). См. Open Questions — это расходится с формулировкой брифа §8.4 «через существующие SQLAlchemy-модели/репозитории».

**Процесс (брифа §9):** PLAN → по волнам (IMPLEMENT → smoke-TEST → локальный коммит) → INTEGRATION_TEST → VISUAL_REVIEW → CODE_REVIEW → DOC_UPDATE → pre-commit gate (архитектор). Волны параллелизма (§7): T1 solo → T2∥T3∥T5 → T4 → T6. DP идёт параллельно фронтовым волнам (backend-only), но обязан быть готов к VISUAL_REVIEW.

**Quality gate каждой фазы (L0, блокирующий):** `make check-fe` ({L0.1}) + `tsc -b && vite build` ({L0.2}) + статические грепы: shadcn-примитивы `shared/ui` руками не правлены ({L0.3}), нет захардкоженных hex/номерных Tailwind-цветов вне токенов в тронутых `.tsx` ({L0.4}), заглушки группы B не вызывают несуществующие endpoint'ы ({L0.5}).

---

## Фазы

### DP: Data-prep — seed-фикстур реальной БД

**Цель:** идемпотентный seed-скрипт наполняет реальную БД детерминированными данными для визуального ревью населённых экранов — через существующие code-paths, без изменения схемы.
**Волна:** 0 (параллельно T1–T5, backend-only; предусловие VISUAL_REVIEW).
**Зона владения (файлы):** `backend/scripts/seed_demo.py` (новый), при необходимости — цель в `Makefile` (`make seed-demo`, согласовать с архитектором — новая цель). Фронтенд не трогает.
**Изменения:**
- Новый async-скрипт по образцу `backend/scripts/grant_admin.py` (`Settings()` → `create_engine` → `create_session_factory` → `async with`). Идемпотентность: проверка существования по уникальным ключам (user.name), upsert-семантика.
- Порядок создания (всё через существующий код, без схемы): (1) User — `hash_password(pw)` → `User(name, password_hash)` → `UserRepository.create`, затем `is_admin=True` (как в `grant_admin.py`) для security-экранов; (2) Project — `ProjectRepository.create`; (3) ≥2 чата — `ThreadViewRepository.create` (PK `thread_id`); (4) сообщения — через LangGraph-checkpointer (`HumanMessage`/`AIMessage`+`.tool_calls`/`ToolMessage`, `additional_kwargs["created_at"]`), включая tool-вызов и инлайн-артефакт (`Artifact.message_id` ← id AI-сообщения через `ArtifactRepository.set_message_id`) — **см. Open Questions по подходу**; (5) артефакты — `ArtifactRepository.create` (`type` — freeform Text); (6) документ сферы — `LangGraphSphereService.update(project_id, content=<markdown ## sections>)`.
- Скрипт — тест-инфраструктура (не продакшен-код), в репозиторий.
**Verification:**
- `{DP.1}` поднят локальный стек (`make docker-up-db` + redis + backend + `make dev-fe`), миграции применены.
- `{DP.2}` скрипт создаёт user(+admin)/project/≥2 чата с сообщениями (user+assistant, tool-вызов, инлайн-артефакт)/артефакты/документ сферы; повторный прогон не дублирует.
- `{DP.3}` (на VISUAL_REVIEW) ревьюер логинится seed-пользователем и достигает населённых экранов.

---

### T1: Фундамент — токены, шрифты, тема, переключатель

**Цель:** заменить нейтральную shadcn-палитру и Geist на брендовые токены «Электрик» light+dark и три шрифта, ввести рабочий переключатель темы; отрефакторить захардкоженные цвета на токены.
**Волна:** 1 (solo — глобальный `index.css`/тема/shell, конфликтный хребет, параллелить нельзя).
**Зона владения (файлы):** `frontend/src/index.css`, `frontend/package.json` (шрифты), `frontend/src/stores/theme-store.ts` (новый), компонент-переключатель в `shared/ui` или `app/components`, точка инициализации темы (`App.tsx`/`app/providers`/`AppLayout`), `frontend/src/app/components/ErrorBoundary.tsx` (только токен-миграция инлайн-цветов), `frontend/src/pages/security/ui/{SeverityBadge,StatusBadge,RuleForm,SecurityRules,SecurityEvents,SecurityAlerts}.tsx` (токен-миграция палитры).
**Изменения:**
- `index.css` — значения токенов light (`:root`) и dark (`.dark`) по таблицам хэндоффа README § Design Tokens (hex приоритетны над OKLCH); радиусы (`--radius: 0.7rem`), доп. цвета (сирень, bubble пользователя). Формат блоков сохранить.
- Шрифты — снять `@fontsource-variable/geist`, добавить три `@fontsource`-семейства: Source Serif 4 (600/700, заголовки/имена сущностей/H-markdown), Instrument Sans (400–700, UI/body), IBM Plex Mono (400/500, версии/таймкоды). Точные пакеты — на реализации (верифицировать по установленному, не по памяти). Подвязать к `@theme` (`--font-sans` = Instrument Sans; serif/mono — свои переменные/утилиты).
- Theme-store (Zustand, селекторы) — `theme: 'light'|'dark'`, вешает/снимает `.dark` на `<html>`, persist в localStorage, инициализация по `prefers-color-scheme` при отсутствии сохранённого выбора. Переключатель — UI-контрол (предложение: user-строка sidebar / user-settings; точную точку определит implementer, но в T1 он должен быть доступен и работать).
- ErrorBoundary — убрать инлайн-hex, перевести на токены (полноценный брендовый error-state с иллюстрацией — в T5, здесь только снятие захардкоженных цветов для {T1.6}).
- Security-бейджи/боксы — Tailwind-палитру (`red/green/blue/yellow-*`) на семантические токены (`destructive`, `muted`, акцент/лаванда и т.п.); сохранить читаемость в обеих темах.
**Verification:**
- L0-гейт (`make check-fe` + `tsc -b && vite build` + грепы {L0.3}/{L0.4}).
- `{T1.1}` `getComputedStyle(:root)`: `--background`≈`#FAF7F1`, `--primary`≈`#7434F4`; `.dark`: `--background`≈`#181420`. Не серая.
- `{T1.2}` font-family заголовков = Source Serif 4, body/UI = Instrument Sans, тех-метки = IBM Plex Mono; Geist отсутствует.
- `{T1.3}` переключатель вешает/снимает `.dark`, вычисленные фон/текст/акцент меняются.
- `{T1.4}` выбор темы переживает перезагрузку (localStorage).
- `{T1.5}` первый заход без сохранения берёт `prefers-color-scheme`.
- `{T1.6}` security-бейджи и ErrorBoundary без захардкоженных цветов, читаемы в обеих темах.

---

### T2: Бренд-примитивы — wordmark K5, знак, Сфера-орб, фавиконы

**Цель:** реализовать брендовые примитивы кодом по спеке хэндоффа и заменить текстовый логотип на wordmark.
**Волна:** 2 (∥ T3 ∥ T5).
**Зона владения (файлы):** новые компоненты в `frontend/src/shared/ui/` (брендовые композиции поверх примитивов — легально по конвенции `shared/ui`): напр. `Wordmark.tsx` (полная + короткая форма через prop), `SphereOrb.tsx`, `BrandMark.tsx`; SVG-фавиконы в `frontend/public/` + линк в `frontend/index.html`. **Точечно** — `app/components/Sidebar.tsx:51` (короткая форма) и `pages/welcome/ui/WelcomePage.tsx:5` (полная форма): замена текста на `<Wordmark/>`.
**Изменения:**
- Wordmark K5 по README § Wordmark: полная форма `LearnFlowAI` («o» во Flow = орб с кольцом и искрой; «AI» цветом `--primary` в рукописном кружке из двух эллипсов); короткая `LearnFlow` (со сферой, без кружка/цветного AI). Instrument Sans 700, letter-spacing −0.015em. Dark-вариант — орб тёмной темы + свечение, текст `#EDE8E2`, акценты `#B194FF`.
- Сфера-орб: радиальный градиент light/dark (единственное место с градиентом в системе), 2 концентрических кольца, искры-ромбы. Параметризовать размером (148px панель / 44px / 16px знак / мини-орб).
- SVG-фавиконы 16/32/180 по спеке знака; подключить в `index.html` (заменить дефолт).
- Замена текстового «LearnFlowAI» на wordmark в Sidebar и WelcomePage.
**Зона пересечения с T3 (seam):** Sidebar.tsx и WelcomePage.tsx правят и T2 (wordmark), и T3 (sidebar-vignette / welcome-hero). Бриф §7 предусматривает короткую интеграцию после волны. Рекомендация оркестратору: правки wordmark (T2, мелкие, 2 строки) приземлять первыми, T3 наслаивает иллюстрации поверх. Остальное в T2/T3 — независимые новые файлы.
**Verification:**
- L0-гейт.
- `{T2.1}` wordmark K5 полная: орб с кольцом/искрой в «o», цветной «AI» в кружке (скриншот vs макет «Проработка 3»).
- `{T2.2}` короткая форма в sidebar/шапках; текстовый «LearnFlowAI» заменён (грепом + визуально).
- `{T2.3}` Сфера-орб: радиальный градиент (light/dark), кольца, искры; градиент только внутри орба (греп отсутствия `gradient` в фоне UI-элементов).
- `{T2.4}` SVG-фавиконы подключены, во вкладке орб.

---

### T3: Ассет-пайплайн + иллюстрации

**Цель:** скопировать cutout-кандидаты в проект, завести централизованную карту ссылок и расставить врезки.
**Волна:** 2 (∥ T2 ∥ T5).
**Зона владения (файлы):** `frontend/src/shared/assets/illustrations/{light,dark}/*.png` (копии 6×2), `frontend/src/shared/assets/illustrations/index.ts` (карта), компонент-обёртка (напр. `shared/ui/Illustration.tsx` — выбирает ассет по `(scene, theme)` из стора темы). Точки вставки врезок: welcome-hero (`pages/welcome`), sidebar-vignette (`app/components/Sidebar.tsx`), empty-states (`pages/project-chats`, `pages/sphere`, `pages/artifacts`), error-state (потребляется T5 в ErrorBoundary).
**Изменения:**
- Скопировать `refs/illustrations/candidates/transparent/soft-balanced/{light,dark}/{welcome-hero,sidebar-vignette,empty-chats,empty-sphere,empty-artifacts,error-state}.png` → `shared/assets/illustrations/{light,dark}/` (имена сцен сохранить).
- Карта `index.ts` — единственная точка свапа (feat-006): отдаёт путь по `(scene, theme)`. Компоненты обращаются только через карту, без прямых импортов png по экранам.
- `Illustration`-обёртка переключает light↔dark по theme-store (зависимость от T1).
- Врезки на места; где ассета по сцене нет/секция пуста — по принципу хэндоффа секцию скрыть, плейсхолдеры в прод не выносить.
**Зона пересечения с T2 (seam):** см. T2 (Sidebar.tsx, WelcomePage.tsx).
**Зависимость:** theme-store из T1.
**Verification:**
- L0-гейт + греп {T3.2}.
- `{T3.1}` 6 сцен × 2 темы скопированы, имена совпадают.
- `{T3.2}` обращение к ассетам только через карту (нет прямых импортов png — грепом).
- `{T3.3}` иллюстрация переключается light↔dark вместе с темой.
- `{T3.4}` врезки на местах: welcome-hero, sidebar-vignette, empty-states, error-state.

---

### T5: Error UX — sonner-тосты + error-bars + ErrorBoundary

**Цель:** дать продукту брендовое отображение ошибок: тосты на API-ошибки, токенизированные error-bars, брендовый ErrorBoundary с иллюстрацией.
**Волна:** 2 (∥ T2 ∥ T3).
**Зона владения (файлы):** `frontend/package.json` (+`sonner`), `frontend/src/shared/ui/sonner.tsx` (примитив через shadcn CLI — генерируется, руками не правим), `frontend/src/app/providers/` (монтаж `<Toaster/>`), `frontend/src/app/providers/QueryProvider.tsx` (onError → toast), `frontend/src/app/components/ErrorBoundary.tsx` (брендовый state).
**Изменения:**
- Установить `sonner`, сгенерировать примитив через CLI base-nova, смонтировать `<Toaster/>` в провайдерах; тема тоста — на токенах, читаема в обеих темах.
- QueryClient onError → тост с сообщением из `shared/lib/api-error.ts` (`getApiErrorMessage`); 4xx-политика без ретраев уже есть в `QueryProvider.tsx` — не дублировать, переиспользовать. Mutations onError тоже на тост.
- ErrorBoundary — брендовое состояние с иллюстрацией error-state из карты T3 (не инлайн-стили). Токен-миграция инлайн-цветов уже сделана в T1; здесь — апгрейд до брендового вида.
**Зависимость:** карта ассетов T3 (для error-state иллюстрации). Тост-инфраструктура (sonner + QueryClient) независима и может строиться сразу; ErrorBoundary-иллюстрацию приземлять после/в интеграции с T3. ErrorBoundary.tsx также трогал T1 (wave 1, секвенциально — без конфликта).
**Verification:**
- L0-гейт (вкл. {L0.3} — sonner.tsx не правлен руками).
- `{T5.1}` при ошибке API (эмуляция 4xx/5xx) показывается тост с сообщением из `api-error`; 4xx не ретраятся.
- `{T5.2}` тосты и error-bars на токенах, читаемы в обеих темах.
- `{T5.3}` ErrorBoundary показывает брендовое состояние с иллюстрацией error-state.

---

### T4a: Каркас (layout shell)

**Цель:** привести геометрию каркаса к числам хэндоффа.
**Волна:** 3 (T4 solo — центральный хребет, под-фазы T4a–T4e секвенциальны одним владельцем).
**Зона владения (файлы):** `frontend/src/app/layouts/{AppLayout,ProjectLayout}.tsx`, `frontend/src/app/components/Sidebar.tsx`.
**Изменения:** sidebar 252px (фон `--sidebar`, граница справа); центр flex:1, контент-колонка max-width 680px по центру (520px при открытой студии); правая панель 318/470px; высота шапок 52–58px; списки/группы — flex/grid с `gap`. Sidebar: wordmark (короткая форма, из T2), «+ Новый чат» primary, «Новый проект» outline, Проекты с точками-статусами, Недавнее, юзер-строка (+ переключатель темы), sidebar-vignette (из T3).
**Verification:** L0-гейт; `{T4.1}` `getComputedStyle`: ширина sidebar 252px, центр-колонка max≈680px, высота шапок 52–58px.

### T4b: Главный экран — чат (на seed-данных)

**Цель:** рестайл ленты чата и инпут-бара по макету «Главный экран».
**Волна:** 3.
**Зона владения (файлы):** `frontend/src/pages/chat/ui/*` (ChatView, ChatHeader, ChatInput, MessageList, MessageItem, ToolIndicator, ReviewIndicator, ArtifactCard, FeedbackButtons).
**Изменения:** bubble пользователя справа со скошенным углом 14/4px; ответ агента плоским текстом; tool-чипы на лаванде с точкой-маркером; карточка артефакта `border-left:3px` акцента; фидбэк «Полезно/Не то/Перегенерировать»; стриминг-индикатор (акцентный прямоугольник 8×16px + текст); инпут-бар card+тень; send — круг 34px primary. ChatHeader: ← проект, название serif, чипы модели/инструментов.
**Verification:** L0-гейт; `{T4.2}` (на seed-данных, vs макет «Главный экран»). Smoke-ревью трека (числа + консоль).

### T4c: Welcome

**Цель:** рестайл welcome-экрана.
**Волна:** 3.
**Зона владения (файлы):** `frontend/src/pages/welcome/ui/WelcomePage.tsx`.
**Изменения:** serif-приветствие 38px, подзаголовок, CTA «+ Новый проект» (primary) и «Продолжить…» (outline), 3 карточки проектов 220px (мини-орб тускнеет с давностью), hero-врезка 460×270 (из T3). Полная форма wordmark (из T2).
**Verification:** L0-гейт; `{T4.3}` (vs макет).

### T4d: Сфера + Артефакты (на seed-данных)

**Цель:** рестайл вьюеров/редактора сферы и списка/вьюера артефактов (группа A — базовый вид).
**Волна:** 3.
**Зона владения (файлы):** `frontend/src/pages/sphere/ui/*` (SphereView/Viewer/Editor), `frontend/src/pages/artifacts/ui/ArtifactList.tsx`, `frontend/src/pages/artifact/ui/ArtifactView.tsx`.
**Изменения:** сфера — viewer markdown (H-serif, маркеры «—» акцентом) + базовый редактор (rich-редактор с тулбаром — группа B, T6); empty-state сферы (из T3). Артефакты — список 318px (иконка типа, выбранный = лавандовая граница + `border-left:3px`), markdown-вьюер: заголовок serif 26px, метаданные, кнопки «Редактировать»(outline)/«.md»(primary)/«.pdf»(outline), контент в card; empty-state артефактов. Вьюеры по типу slides/image/audio — группа B (T6).
**Verification:** L0-гейт; `{T4.4}`, `{T4.5}` (на seed-данных).

### T4e: Проект + Настройки + Sidebar-полировка

**Цель:** рестайл вкладок проекта, настроек пользователя/проекта.
**Волна:** 3.
**Зона владения (файлы):** `frontend/src/pages/project-chats/ui/ChatList.tsx`, `frontend/src/pages/project-settings/ui/ProjectSettingsPage.tsx`, `frontend/src/pages/user-settings/ui/*`, `features/{model-selector,mcp-servers}/ui/*` (визуальная подгонка по макетам), финальная полировка `Sidebar.tsx`.
**Изменения:** Проект — вкладки «Чаты»/«Настройки», табы (активный — акцент + `inset 0 -2px 0`), input нового чата (card+тень, чипы), список чатов (serif-название, превью ellipsis, чипы вклада, дата); настройки проекта (Модель, MCP-серверы со статус-точкой и тогглом, Имя, «Удалить проект…» терракотой). Настройки пользователя `/settings` (одна колонка max 640: Модель, Custom instructions, Память агента, MCP-серверы). Активный пункт юзера подсвечен в sidebar.
**Verification:** L0-гейт; `{T4.6}` (vs макеты); по завершении T4 — `{T4.7}` все экраны A в обеих темах без поломок и ошибок консоли; `{T4.8}` 👤 вкусовой проход (к архитектору).

---

### T6a: Студия-панель S1.2 + линза S2 + peek S3 (заглушки)

**Цель:** новые жесты доступа к сфере из чата на локальном состоянии, без сетевых контрактов.
**Волна:** 4 (после T1,T2,T4).
**Зона владения (файлы):** `frontend/src/pages/chat/` (студия-панель и интеракции — chat-специфичны, по конвенции `features/` только для 2+ страниц → остаются в слайсе чата; размещение ui/model уточнит implementer по FSD). Mock-данные локально.
**Изменения:** студия-панель 470px справа (segmented «Сфера|Артефакты» + ✕; режим артефактов — чипы + мини-вьюер + футер; вход — чип «Студия» в ChatHeader, лаванда при открытой); линза S2 (модал 920×620, скрим, Esc/✕, подсветка фрагмента); peek S3 (разворачиваемая карточка в ленте: шапка на лаванде, mono-чип версии, дифф «+», действия «Открыть/Подправить/Откатить» — откат терракотой). Состояние студии — на уровне чата (локальное, персист по чату — клиентский).
**Verification:** L0-гейт (вкл. {L0.5}); `{T6.1}`, `{T6.2}` (открытие/закрытие, состояние локальное, консоль чиста, вид vs хэндофф).

### T6b: Семвер-UI сферы (заглушки)

**Цель:** UI версионирования сферы на моках.
**Волна:** 4.
**Зона владения (файлы):** `frontend/src/pages/sphere/` (дропдаун версии, история, бейджи). Mock-данные.
**Изменения:** дропдаун «Сохранить версию ▾» (предложение агента предвыбрано, подсвечено лавандой), история версий, бейджи (мажор — заливка primary; минор/патч — лаванда), чип состояния сферы. Никаких сетевых вызовов.
**Verification:** L0-гейт + {L0.5}; `{T6.3}` (на моках, без сети).

### T6c: Вьюеры артефактов по типу + rich-редактор сферы (заглушки)

**Цель:** вьюеры slides/image/audio и rich-редактор сферы на заглушках.
**Волна:** 4.
**Зона владения (файлы):** `frontend/src/pages/artifact/` (вьюеры по type), `frontend/src/pages/sphere/` (rich-редактор с тулбаром). Mock-данные.
**Изменения:** презентация (слайд 16:9 в dark-теме слайдов, лента миниатюр, навигация, .pdf/.pptx); изображение (зум-пилюля, подпись, .png/«Открыть в окне»); аудио (плеер play-круг 40px, прогресс, скорость, табы Саммари/Транскрипт/Заметки, кликабельные mono-таймкоды); rich-редактор (тулбар B/I/H2/H3/список/цитата/код/ссылка/Markdown-режим, автосейв-строка, правый рейл истории). Вьюер выбирается по `type` артефакта; интерактив записи имитируется локальным состоянием.
**Verification:** L0-гейт + {L0.5}; `{T6.4}` (на заглушках), `{T6.5}` (нет обращений к несуществующим endpoint'ам).

---

### DOC_UPDATE: Документация дизайн-соглашений

**Цель:** зафиксировать дизайн-соглашения проекта в документации (решение брифа №8).
**Волна:** финальная (после интеграции, перед арх-гейтом).
**Зона владения (файлы):** `doc/tech/design-system.md` (новый), `doc/tech/conventions.md` (ссылка), `doc/index.md` (ссылка в карте тем).
**Изменения:** новый `doc/tech/design-system.md` — токены, типографика, бренд-примитивы, тема/переключатель, error UX, граница «токены vs захардкоженное», правило «фиолетовый плоский, градиент только в орбе», централизованная карта ассетов. Ссылки из `conventions.md` § Frontend и `doc/index.md`. Констатировать текущее состояние без метапометок итераций (правило CLAUDE.md). Исправить замеченный дрейф на месте, если есть.
**Verification:** ссылки валидны (greps); консистентность с кодом.

---

## Cross-cutting: INTEGRATION_TEST + VISUAL_REVIEW (`track_id=final`)

После интеграции всех волн на feature-ветке — единый прогон агента-визуального-ревьюера (Playwright MCP, без установки в проект) и интеграционные проверки.

**Запуск стека для ревью:** `make docker-up-db` + redis + backend + `make dev-fe`; прогон DP-seed на чистой БД (идемпотентно); логин seed-пользователем (+admin для security). Населённые экраны — на seed-данных; welcome/empty-states — без данных; группа B — на моках.

**Прогон (по каждому экрану в light и dark):** навигация на роут → детерминированные числа через `browser_evaluate`+`getComputedStyle` (токены, ширина sidebar 252px, высота шапок 52–58px, font-family, радиусы, контраст) → скриншот + открытый рядом `.dc.html` как эталон гештальта → сверка → чтение консоли (ноль ошибок/ворнингов). Выход: контактный лист скриншотов всех экранов × тем + триажный отчёт `visual-review-report.md` (артефакты итерации).

**Триаж:** `blocker`/`mismatch` (геометрия/цвет/шрифт/пропавший элемент/ошибка консоли) → цикл фиксов implementer↔ревьюер (≤2 цикла, иначе эскалация), без архитектора; `taste`/«не определить» → к архитектору.

**Verification:**
- `{E2E.1}` 🤖 `vite build` + `make check-fe` зелёные на интегрированной ветке.
- `{E2E.2}` 🔍 полный проход всех экранов light/dark на seed → контактный лист + `visual-review-report.md`.
- `{E2E.3}` 🔍 нет регрессий функциональности (чат, сфера, артефакты, настройки, security).
- `{E2E.4}` 🔍 переключение темы из любого экрана корректно перекрашивает UI и меняет иллюстрации.
- `{E2E.5}` 🔍 консоль без ошибок/ворнингов на основных маршрутах в обеих темах.
- `{E2E.6}` 👤 финальный вкусовой проход архитектора по триажному отчёту и живому UI (+ {T4.8}).

Статус ✅ Done — только после явного апрува архитектора (визуальная приёмка + merge PR). Агент ✅ не ставит. Merge PR в develop — за архитектором локально.

---

## Open Questions

1. **DP — путь сидинга сообщений и сферы.** Бриф §8.4 и `{DP.2}` формулируют seed «через существующие SQLAlchemy-модели/репозитории». Фактически реляционны только User/Project/ThreadView/Artifact; **сообщения чата живут в LangGraph-checkpointer, Сфера — в LangGraph-store** — репозиториев у них нет, путь иной (и более хрупкий). «Без изменения схемы» соблюдается в любом варианте, но подход нужно подтвердить. Варианты для сообщений:
   - **A.** Писать LangChain-сообщения напрямую в checkpointer (`AsyncPostgresSaver`) по форме из `backend/app/agent/checkpoint_history.py`. Детерминированно, но связывает seed с внутренней сериализацией LangGraph (риск дрейфа при апгрейде графа).
   - **B.** Сгенерировать настоящий чекпойнт, один раз прогнав граф агента (нужен доступный/дешёвый/мок-модель; результат менее детерминирован).
   - **C.** Для визуального ревью чата допустить вождение живого агента во время ревью вместо пред-сидинга сообщений (противоречит §8.4 «реальные данные, не агентский кликинг», но снимает связку с checkpointer).
   Какой путь выбрать для сообщений (сфера — аналогично: `LangGraphSphereService.update` против прямой записи в store)? Рекомендация планнера — **A** (детерминизм важнее для воспроизводимого ревью), но это решение об инфраструктуре сидинга — за архитектором.

2. **Новая Makefile-цель `make seed-demo`** (для DP) — добавление цели по конвенции CLAUDE.md требует одобрения архитектора (неочевидное изменение workflow). Подтвердить, или оставить запуск скрипта разовой командой без цели.

Остальные развилки уровня реализации (точные `@fontsource`-пакеты, размещение брендовых компонентов и заглушек группы B по FSD, форма mock-данных, точка размещения переключателя темы) планнер/implementer закрывают по дизайн-системе и FSD-конвенции — эскалация только при многозначности без доминирующего варианта (бриф §11).
