# Summary: feat-013 / трек T1 — Дизайн-система и фундамент состояний

## TL;DR

Все четыре фазы трека T1 реализованы. T1.1: токен `--success` заведён в `frontend/src/index.css` (обе темы + маппинг `--color-success` в `@theme inline`), покрашены его первые потребители — галочка `StatusMeta` в `pages/chat/ui/ActivityRow.tsx` и иконка success-тоста в `shared/ui/sonner.tsx`. Значения токена — канон из мокапа (`#3d7a45` light / `#6fbf78` dark). T1.2: глобальный стиль скроллбаров в `index.css` (webkit-блок 10px + прозрачный трек + hover, Firefox-фолбэк под `@supports not selector(::-webkit-scrollbar)`, `color-scheme` по темам), `scrollbar-gutter: stable` на скролл-контейнерах `MessageList.tsx` и `AppLayout.tsx`. Паритет ширины thumb'а с Base UI `ScrollArea` достигнут и подтверждён замером: видимая полоса у обоих ровно **7px**, тот же цвет токена `--border`, тот же паттерн смещения (подробности — в «Решения и обоснования» T1.2). T1.3: три новые сцены (`not-found`, `artifacts-select`, `auth-hero`) заведены в `shared/assets/illustrations/{light,dark}/` и в централизованную карту `index.ts`. T1.4: контракт волны 2 — `shared/ui/StateScreen.tsx` (три экспорта: `StateScreen`, `LoadingState`, `ErrorCard`) и `shared/ui/skeleton.tsx` (`Skeleton`, сгенерирован канонично `npx shadcn@latest add skeleton` — сеть в сессии была доступна, ручной фолбэк не понадобился). Полный публичный API — ниже в «Решения и обоснования T1.4». `make check-fe`, `make build-fe`, `make test-fe` — зелёные по всему репозиторию (40 test-файлов / 409 тестов), без исключений и без чужих провалов на момент этого прогона. Отступлений от плана и брифа нет, кроме принятых расхождений (Firefox-скроллбар и hover Base UI `ScrollArea` — см. T1.2; ниже — примечание про `animate-pulse` в `Skeleton`, T1.4).

## Реализовано

### T1.1: Токен `--success` и его первые потребители

- `frontend/src/index.css`:
  - `:root` — `--success: #3d7a45;` рядом с блоком MCP-индикаторов (`--mcp-connected`/`--mcp-disabled`), с комментарием роли.
  - `.dark` — `--success: #6fbf78;` в той же позиции.
  - `@theme inline` — `--color-success: var(--success);` добавлен сразу после `--color-destructive-warm`, перед `--color-mcp-connected` (утилита `text-success` теперь резолвится).
- `frontend/src/pages/chat/ui/ActivityRow.tsx`:
  - `StatusMeta`, ветка `success` — `Check` получил `text-success` (было: наследовал `text-muted-foreground` мета-строки). `sr-only` «успешно» не тронут — дублирование канала статуса сохранено. Ветка `error` (`X` → `text-destructive`) не менялась.
- `frontend/src/shared/ui/sonner.tsx`:
  - `icons.success` — `CircleCheckIcon` получил `text-success` рядом с существующим `size-4`. Остальное содержимое файла (структура иконок, стили, тема через `use-theme`) не тронуто.

### T1.2: Скроллбары уровня дизайн-системы

- `frontend/src/index.css`:
  - `:root` — `color-scheme: light;` первой строкой блока токенов, с комментарием: нативные UA-виджеты (в т.ч. нестилизованные фрагменты скроллбара) иначе светятся белым на тёмной теме.
  - `.dark` — `color-scheme: dark;` первой строкой блока.
  - Новый раздел «Скроллбары уровня дизайн-системы (T1.2)» перед секцией `.sphere-prose`:
    - `::-webkit-scrollbar { width: 10px; height: 10px; }` — одна и та же величина для вертикальной и горизонтальной полосы (покрывает и `.sphere-prose pre`, и таблицы SIEM).
    - `::-webkit-scrollbar-track { background: transparent; }`, `::-webkit-scrollbar-corner { background: transparent; }`.
    - `::-webkit-scrollbar-thumb` — `background-color: var(--border); background-clip: padding-box; border-style: solid; border-color: transparent; border-width: 2px 1px 1px 2px; border-radius: 999px;` (подбор рамки под паритет с `ScrollArea` — см. «Решения и обоснования»).
    - `::-webkit-scrollbar-thumb:hover` — `background-color: color-mix(in srgb, var(--muted-foreground) 45%, var(--border));`.
    - `@supports not selector(::-webkit-scrollbar) { :root { scrollbar-width: thin; scrollbar-color: var(--border) transparent; } }` — Firefox-фолбэк строго под гардом (в современном Chromium `scrollbar-width`/`scrollbar-color` тоже поддержаны и без гарда перебили бы webkit-правила).
- `frontend/src/pages/chat/ui/MessageList.tsx`: скролл-контейнер (`<div className="flex-1 overflow-auto p-6">`) получил `style={{ scrollbarGutter: "stable" }}`.
- `frontend/src/app/layouts/AppLayout.tsx`: `<main className="flex-1 overflow-auto">` получил тот же `style={{ scrollbarGutter: "stable" }}`.
- `frontend/src/shared/ui/scroll-area.tsx` — не правился (read-only по резолюции оркестратора п.2 и правилу «shadcn-примитивы руками не правим»).

### T1.4: `StateScreen` и примитивы состояний — контракт волны 2

- `frontend/src/shared/ui/skeleton.tsx` (новый) — сгенерирован канонично: `npx shadcn@latest add skeleton` из `frontend/` (сеть в сессии была доступна, ручной фолбэк не потребовался). Единственная правка после генерации — `prettier --write` (CLI-вывод без части точек с запятой). Публичный API и реализация — штатный shadcn-примитив, содержимое не менял.
- `frontend/src/shared/ui/StateScreen.tsx` (новый) — три экспорта: `StateScreen`, `LoadingState`, `ErrorCard`. Полные сигнатуры — в разделе ниже.

## Решения и обоснования

- Место токена в `:root`/`.dark` — рядом с `--mcp-connected`/`--mcp-disabled` (блок «MCP server status indicators»), как рекомендовано планом («рядом с доменными бренд-токенами»). Отдельного нового блока-заголовка не заводил — токен единичный, а не начало новой группы; комментарий-подпись достаточен по стилю файла (см. соседние однострочные комментарии `/* Terracotta — destructive soft (Delete, Revert) */`).
- Маппинг `--color-success` в `@theme inline` вставлен сразу после `--color-destructive-warm` (первая строка блока) — по аналогии с порядком объявления в `:root`/`.dark`, где `--success` тоже идёт сразу после `--destructive-warm`/перед MCP-токенами. Порядок внутри `@theme inline` в файле не строго следует порядку `:root` (например, `chart-*` и `sidebar-*` идут в обратном относительно `:root` порядке), поэтому это стилистический выбор, не нарушение конвенции.
- Значения токена взяты буквально из мокапа (`ui-polish.html:90` — `--success: #3d7a45;` в `:root`, `ui-polish.html:149` — `--success: #6fbf78;` в `.dark`) и из плана — сверка совпала, дополнительных решений не потребовалось.
- Хардкода hex/rgba в `.tsx`-файлах не вносил — обе правки точечные (`className` += `text-success`), значение токена целиком остаётся в `index.css`.
- `sonner.tsx` — файл в списке задокументированных исключений «shadcn-примитивы руками не правим» (design-system.md § Границы), правка цвета иконки санкционирована брифом 1.1 явно — сверх этого файл не трогал.

- **Подбор рамки thumb'а (паритет ширины с `ScrollArea`, plan-review п.3).** `shared/ui/scroll-area.tsx` (Base UI) держит вертикальный `Scrollbar` шириной `w-2.5` (10px, border-box), но видимый `Thumb` внутри него не 10px: `Scrollbar` несёт `p-px` (padding 1px со всех сторон) и `data-vertical:border-l data-vertical:border-l-transparent` (border-left 1px, только с ведущей стороны, без border-right). Раскладка по ширине: `10 − border-left(1) − padding-left(1) − padding-right(1) = 7px` видимого thumb'а, смещённого на 2px от левого края дорожки и на 1px от правого (для горизонтального `Scrollbar` — тот же расчёт по `border-t`/`padding-top`/`padding-bottom`, смещение 2px сверху / 1px снизу). Чтобы нативный webkit-thumb (который по умолчанию занял бы всю 10px-дорожку) визуально совпал, ему назначена прозрачная рамка с `background-clip: padding-box` и **асимметричной** толщиной `border-width: 2px 1px 1px 2px` (top/right/bottom/left) — те же 2px/1px с той же стороны, что и у `ScrollArea`, а не симметричные 1.5px (которые на устройствах с целочисленным `devicePixelRatio` округлились бы непредсказуемо в 1px или 2px на разных сторонах и разъехались бы с эталоном).
  Замерено эмпирически (не на глаз): собран временный тестовый стенд — `<div overflow-auto>` рядом с реальным `<ScrollArea>` (тот же компонент из `shared/ui/scroll-area.tsx`, с реальным `index.css`), Playwright-скриншот, попиксельный разбор PNG (`PIL.Image.getpixel`). Результат в обеих темах идентичен с точностью до пикселя и до цвета:
  - light: у native — полоса `x=331..337` (**7px**), цвет `rgb(226,220,208)` = `--border` light; у `ScrollArea` — полоса `x=671..677` (**7px**), тот же цвет.
  - dark: у native — полоса `rgb(50,42,68)` = `--border` dark, ширина **7px**; у `ScrollArea` — та же ширина, тот же цвет.
  - Ни в одном кадре не осталось белых/нестилизованных пикселей — `color-scheme` по темам работает.
  Паритет по ширине и цвету достигнут **точно** (7px = 7px, идентичный RGB); паритет по позиции — тем же классом смещения (2px/1px с ведущей/ведомой стороны), без точного попиксельного совпадения абсолютных координат (разные родительские боксы), что визуально неотличимо. Тестовый стенд (`frontend/scratch-scrollbar-test.{html,tsx}`) был временным и удалён после замера — в репозитории не остался.
- **Firefox-фолбэк** — расхождение по ширине/hover принято как норма, зафиксировано брифом (design-brief.md § 1.2) и планом; отдельного эмпирического замера в Firefox не делал (движок недоступен в среде), формула фолбэка (`scrollbar-width: thin` + статичный `scrollbar-color`) — буквально по плану.
- **`scrollbar-gutter`** — вынесен через `style`, а не через Tailwind-класс: именованной утилиты для этого свойства в установленной `tailwindcss@4.2.1` нет (проверено по исходникам пакета в `node_modules`), а arbitrary-property синтаксис Tailwind (`[scrollbar-gutter:stable]`) в плане не упоминается как приоритетный путь — план явно указывает на `style`-паттерн, уже принятый в `MessageList.tsx`.

### T1.4: публичный API `StateScreen`/`skeleton` — контракт волны 2 (T2, T4, T6)

Файлы: `frontend/src/shared/ui/StateScreen.tsx` (три экспорта), `frontend/src/shared/ui/skeleton.tsx` (один экспорт). Полные сигнатуры:

```ts
// shared/ui/skeleton.tsx — канонический shadcn-примитив, сгенерирован CLI
function Skeleton({ className, ...props }: React.ComponentProps<"div">): JSX.Element;
// className={cn("animate-pulse rounded-md bg-muted", className)} — плашка сама несёт animate-pulse.

// shared/ui/StateScreen.tsx
type IllustrationSlot =
  | { scene: Scene; alt: string }
  | { scene?: never; alt?: never }; // сцена и alt — только вместе, типом, не соглашением

type StateScreenProps = IllustrationSlot & {
  title?: string;               // serif-заголовок, опционален
  description: ReactNode;       // единственный обязательный слот
  action?: ReactNode;           // потребитель сам решает Button/Link/вариант
  illustrationClassName?: string; // ширина сцены — см. таблицу ниже
  className?: string;           // root-className, мержится через cn(); flex-1 не прибит намертво
};
function StateScreen(props: StateScreenProps): JSX.Element;

interface LoadingStateProps {
  label?: string;      // дефолт "Загрузка…"
  className?: string;  // растяжка по месту (flex-1 / h-full и т.п.) — по умолчанию не задана
}
function LoadingState(props: LoadingStateProps): JSX.Element;

interface ErrorCardProps {
  message: ReactNode;
  onRetry?: () => void;     // без него — кнопка «Повторить» не рисуется
  retryLabel?: string;      // дефолт "Повторить"
  className?: string;
}
function ErrorCard(props: ErrorCardProps): JSX.Element;
```

Утверждённые ширины сцен (`illustrationClassName`, брать буквально, не пересчитывать): `error-state` 280px, `artifacts-select` 300px, `not-found` 360px, `empty-sphere` 440px, `auth-hero` 460px — передаётся как `"max-w-[280px] w-full"` и т.п.; `StateScreen` не хардкодит ширину сцены сам, это осознанно проп, а не встроенная таблица (разные потребители — разные сцены).

**Явное решение (обязательно к прочтению волной 2): компактные состояния списков собираются из `Skeleton` + `ErrorCard`, `StateScreen` в списках не обязателен.** Геометрия `StateScreen` (`p-8`, `text-2xl` заголовок, `flex-1` центрирование) рассчитана на полноэкранную/панельную форму мокапа (`.state-full`) — в узкую панель (сайдбар 318px, список чатов/артефактов) она не садится, и подгонять её там нечем. T4 при сборке скелетонов списков и inline-ошибок использует `Skeleton`/`ErrorCard` напрямую, без обёртки `StateScreen`.

**Рецепты скелетонов** (эталоны формы для T4, полный код — в JSDoc `StateScreen.tsx`; дублирую здесь, чтобы не идти в чужой файл за ссылкой):

```tsx
// Скелетон карточки чата (список чатов)
<div className="flex flex-col gap-2 rounded-[var(--radius)] p-3">
  <Skeleton className="h-3.5 w-[46%]" />
  <Skeleton className="mt-[7px] h-2.5 w-[68%]" />
  <div className="mt-[9px] flex items-center gap-2">
    <Skeleton className="h-4 w-16 rounded-full" />
    <Skeleton className="mt-[3px] h-2.5 w-[34px]" />
  </div>
</div>

// Скелетон строки артефакта
<div className="flex items-center gap-3 rounded-[var(--radius)] px-3 py-2.5">
  <Skeleton className="h-9 w-9 shrink-0 rounded-[calc(var(--radius)*0.8)]" />
  <div className="flex-1">
    <Skeleton className="h-3 w-[62%]" />
    <Skeleton className="mt-1.5 h-2.5 w-[32%]" />
  </div>
</div>
```

Значения — пиксель в пиксель из мокапа (`.sk-chat`/`.sk-art`, ui-polish.html секция 2а), переведены в Tailwind-утилиты (точные размеры — фиксированной шкалой где совпадает, `w-16`/`h-4`/`h-9`/`mt-1.5`; где не совпадает — arbitrary-значением, `w-[46%]`/`mt-[7px]` и т.п.).

**Решение про `Skeleton` и генерацию.** По резолюции оркестратора (Open Question 1 / plan-review п.1) сначала опробована каноничная генерация — `npx shadcn@latest add skeleton` из `frontend/`. Сеть в этой сессии оказалась доступна (вопреки ожиданию плана «нет сети — ожидаемо в песочнице»), CLI создал ровно один файл (`shared/ui/skeleton.tsx`), никаких сопутствующих правок в `package.json`/`components.json`/других файлах — проверено по `git status` до и после генерации. Файл не редактировался руками, кроме прогона `prettier --write` (CLI-вывод пришёл без части точек с запятой — под конфиг проекта не подпадал). Итог: ручной фолбэк не понадобился, будущая перегенерация ляжет на то же место без риска дублей.

**Расхождение с телом фазы T1.4 плана (не с резолюцией/plan-review): `animate-pulse` — на каждой плашке `Skeleton`, а не на контейнере группы.** Тело фазы (строка «а `animate-pulse` вешается на контейнер группы, а не на каждую плашку») описывало вариант «свой» `Skeleton` без анимации внутри. Канонический shadcn-примитив, который реально сгенерировался, несёт `animate-pulse` в себе на каждый инстанс — это же поведение прямо описано и в тексте резолюции оркестратора («плашка на `--muted` + `animate-pulse`», Open Question 1), то есть сам `Skeleton` уже включает пульсацию как часть контракта. Рецепты выше поэтому не оборачивают группу в дополнительный `animate-pulse`-контейнер — это было бы дублирующей анимацией поверх уже пульсирующих плашек. Визуально расхождения с мокапом нет: все плашки монтируются в один кадр и стартуют анимацию синхронно (общий keyframe, без случайной задержки), эффект неотличим от group-level пульса. Если архитектор сочтёт это отклонением от буквы плана — правка тривиальна (снять `animate-pulse` с примитива, добавить его в рецепты на уровне контейнера), но тогда `Skeleton` разойдётся с каноническим shadcn-выводом и следующая перегенерация её сотрёт.

## Follow-ups

- **Дрейф `doc/tech/design-system.md`** (§ Темизация, строка 95; § Иллюстрации, строка 110): документ утверждает, что `Illustration` и обёртка `sonner` подписаны на `theme-store` через селектор, тогда как фактически оба читают тему хуком `shared/lib/use-theme` через DOM (`.dark` на `<html>`, `useSyncExternalStore`), намеренно не завися от `stores` (граница FSD `shared → shared`). Правка — фазой DOC_UPDATE после барьера, трек T1 `doc/` не правит.
- **Hover-паритет Base UI `ScrollArea`** (кандидат из плана, `Open Question 2` / резолюция оркестратора п.2) — **актуализировано после T1.2**: глобальный скроллбар получил hover-усиление (`::-webkit-scrollbar-thumb:hover`), у `ScrollArea` его нет, и без правки сгенерированного `scroll-area.tsx` (запрещена резолюцией оркестратора п.2 / `conventions/frontend.md` § Граница shadcn) паритет недостижим. Расхождение принято как норма — того же рода, что и Firefox-фолбэк. Ширина и цвет thumb'а при этом доведены до точного паритета (см. «Решения и обоснования» T1.2, замер 7px=7px в обеих темах) — расхождение сузилось строго до hover. Выравнивание возможно только переносом `ScrollArea` в собственные композиции проекта — решение архитектора, вне скоупа T1.

## SOFA-посты (id / применил / результат)

