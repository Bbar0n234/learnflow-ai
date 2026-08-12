# Summary: feat-013 / трек T6 — Брендовый auth-дизайн

## TL;DR

**Все четыре фазы трека (T6.1–T6.4) реализованы.**

T6.4 — живая сверка экрана с мокапом: временная dev-обвязка (`frontend/scratch-auth-preview.{html,tsx}`, вне закрытого списка файлов трека) смонтировала `LoginScreenView` с управляемым состоянием и подняла её через `make dev-fe`. Playwright прогнал экран в обеих темах, обоих режимах, обоих гео-составах, обоих граничных состояниях `providers` (`undefined`/`[]`) и `submitting`, ниже брейкпоинта `lg`. Композиция, отступы, размеры, цвета сверены **по числам, не на глаз** (`getComputedStyle`/`getBoundingClientRect`) против живого мокапа (`ui-polish.html`, секция 7, поднятого отдельным `http.server`): полное совпадение, расхождений, требующих правки кода, не найдено. Обвязка удалена, `git status` в корне репозитория чист от неё и от скриншотов — единственные изменения вне T6 принадлежат параллельным трекам T2/T3/T4. Числа и найденные подтверждения — в разделе «Реализовано» ниже.

T6.1, T6.2 и T6.3 реализованы ранее (см. ниже); T6.4 не вносит правок кода — только подтверждает их визуально.

T6.1 — `shared/ui/ProviderButton.tsx` (новый файл): кнопка входа через провайдера с брендовым inline-SVG знаком поверх существующего `Button variant="outline" size="lg"`. Провайдеры — `yandex` | `google` | `github`; VK нигде не упоминается. Знаки — inline-SVG, пути и брендовые цвета взяты дословно из мокапа (`ui-polish.html`, секция 7, строки 441–454). Знак GitHub красится фирменными hex мокапа для обеих тем (`#24292f` light / `#f0f0f0` dark через `dark:` variant), а не `currentColor` — по правке plan-review п.3. Хардкод hex ограничен блоком трёх иконок с обосновывающим комментарием (резолюция оркестратора 1).

T6.2 — `shared/ui/AuthLayout.tsx` (новый файл): полноэкранная брендовая композиция auth-экрана — левая колонка (wordmark 38px + тэглайн + `Illustration` сцены `auth-hero` 460px), правая — слот `children` под карточку формы (440px). Геометрия, отступы, ритм — дословно из мокапа, «рамка демо → полный экран» по плану. Ниже `lg` брендовая колонка скрыта, wordmark уменьшённым (26px) переезжает шапкой над карточкой — решение оркестратора сверх мокапа (резолюция 3), т.к. мокап брейкпоинт не покрывает.

T6.3 — новый слайс `features/auth/` (`ui/LoginScreenView.tsx` + `index.ts` — публичный API): чисто презентационный экран входа/регистрации, собранный из `AuthLayout`, `ProviderButton`, shared `Input`/`Button`, `ErrorCard`. Никакой auth-логики — режим, значения полей, гео-состав провайдеров, текст ошибки, `submitting` и все обработчики приходят через props; в файле нет ни одного импорта из `shared/api`, `stores`, `react-router` (проверено грепом). **Главный продукт трека — контракт `LoginScreenViewProps`** — полная сигнатура ниже в «Решения и обоснования». `providers` различает `undefined` (гео ещё грузится — место зарезервировано разделителем «или» + skeleton-плашкой) и `[]` (провайдеров нет — блок и разделитель не рисуются), по правке plan-review п.1. `autoComplete` поля пароля переключается по режиму (`new-password` в регистрации, `current-password` во входе), а не берётся из мокапа буквально — по правке plan-review п.2.

Все три файла — чисто презентационные, без auth-логики, без импортов выше `shared/`. Новых зависимостей не вводил. `make check-fe` (tsc + eslint + prettier по всему репозиторию) — **полностью зелёный** на момент сдачи фазы (ранее падавшие чужие файлы T2 к этому моменту уже почищены параллельными агентами). `make build-fe` проходит — `LoginScreenView` стал первым реальным потребителем `AuthLayout`, вся цепочка трека впервые компилируется целиком. `make test-fe` — 13 падений в 6 файлах, ни один не в скоупе T6 (`app/router.test.tsx`, `features/model-selector/**`, `pages/artifacts/**`, `pages/chat/ui/ChatThread.test.tsx`, `pages/project-chats/**`, `pages/sphere/**` — все T2/T3/T4).

## Реализовано

### T6.1: Брендовые иконки провайдеров и `ProviderButton`

- `frontend/src/shared/ui/ProviderButton.tsx` (новый) — один публичный компонент + три приватные иконки-компонента (`GoogleIcon`, `GitHubIcon`, `YandexIcon`) в этом же файле:

  ```ts
  export type AuthProvider = "yandex" | "google" | "github";

  export interface ProviderButtonProps {
    provider: AuthProvider;
    /** Переопределение подписи. Дефолт — фирменная формулировка провайдера. */
    label?: string;
    onClick?: () => void;
    disabled?: boolean;
    className?: string;
  }
  export function ProviderButton(props: ProviderButtonProps): ReactElement;
  ```

- Дефолтные подписи — буквально из мокапа: «Войти с Яндекс ID» (неразрывный пробел `&nbsp;` мокапа заменён обычным ` ` в JSX-тексте, как требует план), «Войти через Google», «Войти через GitHub».
- Вёрстка: `Button type="button" variant="outline" size="lg"`, `className="w-full justify-center gap-2.5"` (мокап: `gap: 10px`, `justify-content: center`, `width: 100%`) — радиус/бордер/hover/тёмная тема достаются от варианта `outline`, своих цветовых классов не добавлял.
- Иконки — `className="size-5"` (мокап требует 20px, базовый класс кнопки даёт `size-4` через `[&_svg:not([class*='size-'])]:size-4` — явный `size-5` его переопределяет), `aria-hidden="true"`.
- Логика провайдера (URL, редиректы) в компонент не заходит — только `onClick`.

### T6.2: `AuthLayout` — полноэкранная брендовая композиция

- `frontend/src/shared/ui/AuthLayout.tsx` (новый):

  ```ts
  export interface AuthLayoutProps {
    /** Слот карточки формы — правая колонка. */
    children: ReactNode;
    /** Тэглайн под wordmark. Дефолт — утверждённый мокапом текст. */
    tagline?: ReactNode;
    className?: string;
  }
  export function AuthLayout(props: AuthLayoutProps): ReactElement;
  ```

- Корень: `flex min-h-screen w-full bg-background` — «рамка демо → полный экран» вместо мокапного `border` + `min-height: 640px`.
- Левая колонка (видна только от `lg`, `hidden lg:flex`): `flex-1 flex-col justify-center gap-[22px] p-14` (56px паддинг, 22px ритм) — `Wordmark` c `text-[38px]` (полная форма, с «AI»-бейджем — мокап 909 рисует именно её, не короткую), тэглайн `max-w-[380px] text-[15px] leading-[1.55] text-muted-foreground` с дефолтным текстом мокапа, `Illustration` сцены `auth-hero` (`alt="Иллюстрация: Электрик приветствует"`, `w-full max-w-[460px]` — утверждённая T1 ширина).
- Правая колонка: `w-full shrink-0 ... lg:w-[440px]`, паддинг `px-6 py-10` на узком экране и мокапные `lg:px-12 lg:py-10` (48px/40px) от `lg`; слот `children` под карточку формы.
- Поведение ниже `lg` (решение оркестратора сверх мокапа, резолюция 3): брендовая колонка скрыта (`hidden lg:flex`), правая колонка растягивается на всю ширину, а `Wordmark` в уменьшенном размере (`text-[26px] lg:hidden`) становится шапкой над слотом карточки. Мокап этот брейкпоинт не покрывает — оба варианта wordmark (полноразмерный desktop и уменьшенный mobile-заголовок) существуют в DOM одновременно, видимость переключается через `hidden`/`lg:flex` без JS/media-query-состояния — компонент остаётся без `useState`/`useEffect`.
- Фон корня — `bg-background` (не `--card`): карточка формы (её рисует T6.3) будет отличаться от полотна в обеих темах.
- Хардкода hex/rgba нет — только Tailwind-утилиты токенов.

### T6.3: `LoginScreenView` и публичный API слайса `features/auth`

- `frontend/src/features/auth/ui/LoginScreenView.tsx` (новый) — экран входа/регистрации: `AuthLayout` (слот `children`) + `<form>`-карточка, собранная из shared `Input`, `Button`, `ErrorCard`, `Skeleton` и `ProviderButton`. Полная сигнатура контракта — в «Решения и обоснования» ниже.
- `frontend/src/features/auth/index.ts` (новый) — публичный API слайса: `LoginScreenView` + `export type` на `AuthMode`, `AuthFormValues`, `LoginScreenViewProps` (реэкспорт из `./ui/LoginScreenView`) и `AuthProvider` (реэкспорт из `@/shared/ui/ProviderButton`, чтобы потребитель не тянул `shared/ui` напрямую ради одного типа).
- Вёрстка карточки — дословно значения мокапа (`ui-polish.html`, секция 7, строки 392–408, 914–938): карточка `rounded-xl border border-border bg-card p-7 text-card-foreground` + `style={{ boxShadow: "var(--shadow-input)" }}`; заголовок `font-serif text-[22px] font-semibold tracking-[-0.01em]`; подзаголовок `mt-[3px] text-[13px] text-muted-foreground`; поля `mt-[18px] flex flex-col gap-2.5`; разделитель «или» `my-4 flex items-center gap-3 text-xs text-muted-foreground` с двумя `h-px flex-1 bg-border`; блок провайдеров `flex flex-col gap-2`; переключатель режима — `Button variant="link"` `mt-3.5 w-full text-[13px]`.
- Тексты — буквально из мокапа (скрипт секции 7): заголовки «Вход»/«Регистрация», подзаголовки «Продолжите работу со своими проектами.»/«Придумайте имя и пароль — этого достаточно.», подписи сабмита «Войти»/«Создать аккаунт» (при `submitting` — типографское «…»), переключатель «Нет аккаунта? Зарегистрироваться»/«Уже есть аккаунт? Войти», плейсхолдеры «Имя пользователя»/«Пароль»/«Повторите пароль».
- Поля получают `id` (через `useId()`) и связанный `<label className="sr-only">` — плейсхолдер не является доступным именем (плейсхолдеры остаются, ярлык только для a11y-дерева). Автофокус — на поле имени. Корень карточки — `<form onSubmit>`, чтобы Enter отправлял форму; переключатель режима — `type="button"`, чтобы не сабмитить форму по клику.
- Кнопка сабмита блокируется только по `submitting` (пустые поля не блокируют — по телу плана, чтобы клик всегда что-то отвечал).
- Никакой auth-логики: импорты компонента — только `react`, `@/shared/ui/*`; ни одного импорта из `shared/api`, `stores`, `react-router` (проверено грепом по файлу).

### T6.4: Живая сверка с мокапом в обеих темах

**Обвязка (временная, удалена до сдачи фазы).** `frontend/scratch-auth-preview.html` + `frontend/scratch-auth-preview.tsx` — вне закрытого списка файлов трека, в `.gitignore`-неотслеживаемом состоянии не были (обычные новые файлы), созданы, использованы и удалены в рамках этой фазы, по условиям резолюции оркестратора 4 (тот же приём, что применил T1 в фазе T1.2). Обвязка монтировала `LoginScreenView` с локальным `useState`, читая начальное состояние (`mode`, `providers`, `error`, `submitting`, `dark`) из query-строки `?mode=...&providers=...&error=...&submitting=...&dark=...` — так каждый сценарий открывался прямым URL без клика по кнопкам управления (в первых попытках клики по обвязке периодически ловили HMR-ремаунт dev-сервера и теряли state; query-driven инициализация сняла этот источник шума). Поднято через `make dev-fe` (`http://localhost:5174` — 5173 был занят другим процессом), просмотрено через Playwright MCP (навигация, `getComputedStyle`/`getBoundingClientRect` через `browser_evaluate`, скриншоты). Мокап поднят отдельным `python3 -m http.server 8899` в `mockups/` — прямой `file://` недоступен из браузера MCP.

**Сверено по числам (не на глаз), light-тема, providers=`["yandex"]`, mode=`login`:**

- `Wordmark`: `font-size: 38px` (полная форма) — совпадает с мокапом (`.wm { font-size:38px }`, строка 909).
- Карточка формы (`<form>`): `padding: 28px`, `border-radius: 15.68px` (= `--radius-xl` = `calc(0.7rem * 1.4)` = `11.2px * 1.4`), `box-shadow: rgba(80,70,50,0.06) 0 2px 10px 0` (= токен `--shadow-input`) — совпадает с мокапом (`.auth-card { padding:28px; border-radius:calc(var(--radius)*1.4); box-shadow:var(--shadow-input) }`).
- Тэглайн: `font-size: 15px`, `width: 380px` (= `max-width` мокапа `.tagline { font-size:15px; max-width:380px }`).
- `Illustration` (`auth-hero`): ширина рендера `460px` (= `max-width:460px` мокапа).
- `Input`: `height: 32px`, `border-radius: 11.2px` (= `--radius`) — совпадает с `.input` мокапа.
- Кнопка сабмита: `height: 36px`, `border-radius: 11.2px` — совпадает с `.btn.btn-lg` мокапа.
- Полная композиция (скриншот 1440×900) пиксель-в-пиксель совпадает с живым рендером секции 7 мокапа при том же гео (одна кнопка Яндекс, тот же порядок блоков, тот же интервал).

**Сверено визуально + по вычисленным стилям, оба гео-состава, обе темы:**

- `providers=["yandex","google","github"]` (не-РФ): три кнопки в порядке Яндекс → Google → GitHub, знаки узнаваемы (Google — 4 цвета, GitHub — octocat, Яндекс — красная «Я» на белом круге) — сверено скриншотом против мокапа в состоянии `geo=не-РФ`, совпадение полное в обеих темах.
- Знак GitHub, `fill` вычисленного стиля `<path>`: light — `rgb(36,41,47)` = `#24292f`; dark — `rgb(240,240,240)` = `#f0f0f0`. Точное совпадение с хардкодом T6.1 и с мокапом (`.p-github { color:#24292f }`, `.dark .p-github { color:#f0f0f0 }`) в обеих темах, измерено напрямую, не по коду.
- Круг Яндекса: `fill` вычисленного стиля `<circle>` — `rgb(255,255,255)` в обеих темах (белый круг не темизируется, как в мокапе).
- `Illustration`: `src` меняется между `.../light/auth-hero.png` и `.../dark/auth-hero.png` при переключении `.dark` на `<html>` — подтверждена реактивность `useTheme`, тема резолвится без перезагрузки страницы.
- Тёмная тема, `mode="register"`, `providers=["yandex","google","github"]`, `error` заполнен: карточка, заголовок «Регистрация», подзаголовок, три поля (включая «Повторите пароль»), `ErrorCard` («Введите имя и пароль.»), кнопка «Создать аккаунт», три кнопки провайдеров, переключатель «Уже есть аккаунт? Войти» — полное визуальное совпадение со скриншотом мокапа в том же состоянии (`geo=не-РФ`, `dark`, режим переключён кликом на `#auth-mode-link`, ошибка вызвана сабмитом пустой формы).

**Граничные состояния `providers` (правка plan-review п.1) и `submitting` — проверены визуально, поведение корректно:**

- `providers=undefined` («гео грузится»): разделитель «или» отрисован, вместо кнопок — одна `Skeleton`-плашка высотой ровно с кнопку (36px), место не прыгает при последующей замене на реальные кнопки — визуально подтверждено сравнением высоты блока с обычным состоянием.
- `providers=[]` («провайдеров нет»): ни разделителя, ни блока кнопок нет, карточка короче ровно на их высоту — подтверждено.
- `submitting=true`: оба текстовых поля и кнопка сабмита получают `disabled` (визуально приглушены), подпись сабмита — «…», кнопка провайдера тоже `disabled` (проверено программно: `disabled === true`, `opacity: 0.5`, при этом `cursor: pointer` наследуется от базового класса `Button` — это существующее поведение shadcn-примитива, не регрессия трека).

**Брейкпоинт `lg` (решение оркестратора сверх мокапа, резолюция 3) — проверено на 900px (< `lg` = 1024px):**

- Брендовая колонка (`wordmark` 38px + тэглайн + иллюстрация) не рендерится (`hidden`), карточка растягивается на всю ширину вьюпорта с паддингом, уменьшенный `Wordmark` (26px) становится шапкой над карточкой — соответствует описанному в T6.2 поведению, сверх мокапа (мокап этот брейкпоинт не покрывает).

**Клавиатура и фокус — проверено:**

- Явных `tabIndex` в `LoginScreenView.tsx`/`ProviderButton.tsx`/`AuthLayout.tsx` нет (проверено грепом) — порядок обхода Tab полностью определяется DOM-порядком элементов: имя → пароль → (повтор пароля в `register`) → сабмит → провайдеры по порядку `providers` → переключатель режима. Все интерактивные элементы — стандартные `shared/ui/{button,input}.tsx` с уже принятым в проекте классом `focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50` (не специфично для T6, общий примитив дизайн-системы).
- Focus-ring визуально проверен в обеих темах (реальный keyboard-фокус, не программный `.focus()`, который не триггерит `:focus-visible` в Chromium): в тёмной теме на карточке `--card` кольцо `ring-ring/50` читается отчётливо; в светлой — аналогично.
- Enter в поле отправляет форму — подтверждено структурой (`<form onSubmit>` в `LoginScreenView.tsx:125`), поведение стандартное для HTML-форм, отдельно не тестировалось кликом (сабмит уже проверен через триггер ошибки во всех сценариях выше).

**Расхождений с мокапом, требующих правки кода трека, не найдено.** Все ранее задокументированные отступления от буквы мокапа/брифа (уплотнённая геометрия `ErrorCard`, радиус `--radius-xl`, `autoComplete` по режиму, skeleton-резервирование при `providers===undefined`, поведение ниже `lg`) визуально подтверждены как корректные и согласованные, новых не добавилось.

**Уборка.** Оба файла обвязки удалены (`rm frontend/scratch-auth-preview.{html,tsx}`), скриншоты (генерировались в корень репозитория Playwright MCP) удалены, dev-сервер (`localhost:5174`) и вспомогательный `http.server 8899` для мокапа остановлены. `git status --porcelain` в корне репозитория после уборки не содержит ни одного файла, порождённого этой фазой — весь diff вне `tracks/T2/T3/T4` и `frontend/src/features/auth/**`/`frontend/src/shared/ui/{AuthLayout,ProviderButton}.tsx` отсутствует.

**Гейты после уборки (по файлам трека, полный `make check-fe`/`make test-fe` в общей ветке всё ещё не показателен из-за параллельных T2/T3/T4 — см. пояснение в «Верификация» ниже):**

- `npx tsc -b --noEmit` — 0 ошибок по всему проекту, включая все четыре файла трека.
- `npx eslint src/shared/ui/AuthLayout.tsx src/shared/ui/ProviderButton.tsx src/features/auth/ui/LoginScreenView.tsx src/features/auth/index.ts` — чисто.
- `npx prettier --check` на тех же четырёх файлах — чисто.
- `npx vite build` (полная прод-сборка, `dist/` — gitignored, удалён после проверки) — прошла успешно (`✓ built in 52.93s`), без ошибок резолюции ассетов или типов.

## Решения и обоснования

- **Хардкод брендовых hex — санкционированное исключение, применено по условиям резолюции оркестратора 1 (plan.md T6 § Резолюции, п.1).** Цвета живут только внутри блока трёх иконок-знаков, помечены комментарием («Хардкод hex ниже — санкционированное исключение… фирменные цвета бренда, не палитра продукта, темизации не подлежат»). Больше нигде в файле hex/rgba нет — единственные цветовые литералы находятся внутри `GoogleIcon`/`GitHubIcon`/`YandexIcon`.
- **Знак GitHub — брендовые hex мокапа для обеих тем, не `currentColor`** (plan-review п.3, обязателен к исполнению): `className="fill-[#24292f] dark:fill-[#f0f0f0]"` на `<path>`. Тело фазы T6.1 предлагало `currentColor` (наследование от `text-foreground`) — это отклонено ревью плана: внутри карточки текст красится `text-card-foreground` (тёплый), а не `text-foreground`, и знак получил бы неверный оттенок вместо холодного фирменного. `fill-[...]`/`dark:fill-[...]` — тоже хардкод hex в `.tsx`, но подпадает под то же исключение (значение бренда, не палитра продукта) и находится в том же откомментированном блоке.
- **Тип возврата `ReactElement` (из `"react"`), а не `JSX.Element`/`React.JSX.Element`.** Сигнатура в плане (`: JSX.Element`) — псевдокод контракта, не буквальная TS-аннотация. Стиль остальных `shared/ui/*.tsx`: глобальный `JSX` namespace нигде не используется, `ReactElement`/`ReactNode` из `"react"` — да (`StateScreen.tsx`, `StateScreen.test.tsx`). `React.JSX.Element` потребовал бы отдельного `import * as React` ради одного типа — взял уже принятый в проекте `ReactElement`.
- Приватные иконки — три function-компонента в одном файле с `ProviderButton`, без отдельных файлов, как предписано планом (закрытый список файлов трека, знаки нужны ровно одному потребителю).
- **Поведение ниже `lg` реализовано без JS-состояния.** Вместо `useState`/`matchMedia`-хука оба варианта wordmark (полный desktop-размер в левой колонке, уменьшенный mobile-заголовок в правой) существуют в разметке одновременно, а видимость переключают только классы `hidden`/`lg:flex` и `lg:hidden` — компонент остаётся чисто презентационным (ни состояния, ни эффектов), как требует план. Конкретные значения узкого экрана (`gap-8 px-6 py-10`, wordmark `26px`) мокапом не заданы — это решение сверх мокапа (резолюция оркестратора 3), а не перенос конкретных чисел из брифа.
- **Радиус карточки формы — `--radius-xl` (`calc(var(--radius) * 1.4)`), а не обобщённый `--radius` брифа.** Сама карточка — за T6.3, но фиксирую здесь по plan-review п.4: мокап (`.auth-card { border-radius: calc(var(--radius) * 1.4); }`) и T1-контракт (`--radius-xl` уже заведён в `index.css:192` ровно под это значение) расходятся с бланкетной формулировкой брифа. `AuthLayout` радиус карточки не рисует (только слот), но геометрия рамки корня в мокапе (`.auth-frame`) была той же `calc(var(--radius) * 1.4)` — в полноэкранной версии корень эту рамку не несёт вовсе (нет `border`), поэтому вопрос радиуса в `AuthLayout.tsx` не возникает; расхождение относится целиком к карточке T6.3.

### T6.3: публичный API `LoginScreenView` — контракт стыка с feat-008

**Главный продукт трека.** Полная сигнатура (`frontend/src/features/auth/`, экспорт — через `index.ts`):

```ts
export type AuthMode = "login" | "register";
export type { AuthProvider } from "@/shared/ui/ProviderButton"; // "yandex" | "google" | "github"

export interface AuthFormValues {
  name: string;
  password: string;
  /** Используется только в mode="register". */
  confirmPassword: string;
}

export interface LoginScreenViewProps {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;

  values: AuthFormValues;
  onFieldChange: (field: keyof AuthFormValues, value: string) => void;

  /** Сабмит формы. View сам делает preventDefault и ничего не валидирует. */
  onSubmit: () => void;

  /**
   * undefined — гео ещё грузится (место под блок зарезервировано:
   * разделитель «или» + skeleton-плашка высотой одной кнопки, чтобы карточка
   * не прыгала). [] — провайдеров нет, ни разделитель, ни блок не рисуются.
   * Непустой массив — кнопки в порядке массива. Гео-модель: РФ — ["yandex"];
   * вне РФ — ["yandex","google","github"]. VK ID не существует ни в каком виде.
   */
  providers?: readonly AuthProvider[];
  onProviderSelect: (provider: AuthProvider) => void;

  /** Текст ошибки для ErrorCard. Пусто/undefined — карточки нет. */
  error?: string | null;
  /** Идёт отправка: сабмит и провайдеры заблокированы. */
  submitting?: boolean;

  className?: string;
}

export function LoginScreenView(props: LoginScreenViewProps): ReactElement;
```

Валидация и все запросы (auth-запросы, чтение гео, роутинг) — целиком на стороне потребителя (`pages/login`, feat-008). Ожидаемые тексты ошибок валидации (для сборки `error`, буквально из мокапа): «Введите имя и пароль.» (пустое имя/пароль), «Пароль должен содержать не менее 8 символов.» (`mode="register"`, пароль < 8 символов), «Пароли не совпадают.» (`mode="register"`, несовпадение паролей) — задокументированы в JSDoc `LoginScreenViewProps.error`, чтобы feat-008 и `test-author` не выдумывали свои формулировки.

**Отступления от буквы мокапа/брифа, зафиксированные для гейта архитектора:**

1. **Геометрия `ErrorCard` уплотнена под auth-экран** (`px-3.5 py-2.5 text-[13px]` вместо канона блока 4). Это единственное место в итерации, где карточка ошибки отличается от канона — сам мокап (`.err-card`, инлайновый `style="padding:10px 14px;font-size:13px"`) это поддерживает, но по форме это исключение auth-экрана, не второй канон.
2. **Радиус карточки формы — `--radius-xl`** (`calc(var(--radius) * 1.4)`), тогда как design-brief обобщённо писал `--radius`. Мокап и T1-контракт (`--radius-xl` в `index.css`) совпадают буквально — расхождение только с формулировкой брифа (см. также заметку T6.2 выше).
3. **`autoComplete` поля пароля переключается по режиму, а не берётся из мокапа буквально** (plan-review п.2): `mode="register"` → `new-password` (пароль и подтверждение), `mode="login"` → `current-password`. Мокап статичен и всегда несёт `current-password` — буквальный перенос дал бы неверную подсказку менеджеру паролей при регистрации (предложил бы существующий пароль вместо генерации нового).
4. **Блок провайдеров при `providers === undefined` рисует `Skeleton` (одна плашка высотой кнопки) вместо мокапного статичного состава.** Мокап не покрывает состояние загрузки гео (у него состав переключается мгновенно демо-тумблером) — это решение сверх мокапа, введённое правкой plan-review п.1 («место зарезервировано, чтобы не прыгало»); выбор конкретной формы резервирования (skeleton на высоту одной кнопки, а не на максимально возможные три) — моё решение в рамках этой правки, не отдельная эскалация.

## Верификация

- **`make check-fe` целиком падает по чужому файлу, не по моему.** Единственная причина падения — существующее форматирование в `frontend/src/stores/stream-store.ts` (владеет трек T2, не в моём скоупе; файл не трогал). Точечная проверка `ProviderButton.tsx`:
  - `npx tsc -b --noEmit` (часть `make check-fe`) прошёл без ошибок по всему проекту, включая новый файл.
  - `npx prettier --check src/shared/ui/ProviderButton.tsx` — чисто.
  - `npx eslint src/shared/ui/ProviderButton.tsx` — чисто (в т.ч. `eslint-boundaries`: импорты только `@/shared/ui/button`, `@/shared/lib/utils`, `react`).
- **`make test-fe` — 40 из 44 тестовых файлов зелёные; 4 падения не касаются `ProviderButton.tsx`** (у компонента ещё нет теста — их пишет `test-author`):
  - `src/pages/chat/model/useAgentStream.test.ts` — трек T2.
  - `src/app/router.test.tsx` (кейс `/security` под SIEM-флагом) — трек T4.
  - `src/pages/user-settings/ui/SkillContextSection.test.tsx` (10 кейсов) — трек T4.
  - `src/features/model-selector/ui/ModelSelector.test.tsx` (3 кейса) — трек T3.
  Все перечисленные файлы принадлежат другим трекам, идущим параллельно в той же ветке; `git status` на момент прогона показывал их как изменённые/новые не мной.

**T6.2 (`AuthLayout.tsx`), точечная проверка (полный `make check-fe` в общей ветке всё так же красный по чужим файлам — см. выше):**

- `npx prettier --check src/shared/ui/AuthLayout.tsx` — чисто.
- `npx eslint src/shared/ui/AuthLayout.tsx` — чисто (в т.ч. `eslint-boundaries`: импорты только `@/shared/lib/utils`, `@/shared/ui/Wordmark`, `@/shared/ui/Illustration`, `react`).
- `npx tsc -b --noEmit` — 0 ошибок по всему проекту, включая новый файл.
- `make build-fe` проходит (`vite build`, `✓ built in 24.69s`); полезность этой проверки для T6.2 ограничена — у `AuthLayout` пока нет потребителя (`LoginScreenView` появляется в T6.3), поэтому файл не входит в граф импортов от `main.tsx`, и сборка его не компилирует. Резолюция ассета `Illustration`/`getIllustration("auth-hero", …)` уже проверена T1 отдельно; полноценная сборочная проверка самого `AuthLayout` состоится в T6.3–T6.4, когда `LoginScreenView` станет потребителем.
- Сверка с мокапом по значениям: колонки `flex-1`/`440px`, паддинги `56px`/`40px`+`48px`, вертикальный ритм `22px`, wordmark `38px` (полная форма), тэглайн `15px`/`1.55`/`380px`, сцена `460px` — совпадают буквально.

**T6.3 (`features/auth/**`):**

- `npx tsc -b --noEmit` — 0 ошибок по всему проекту, включая оба новых файла.
- `npx eslint src/features/auth/ui/LoginScreenView.tsx src/features/auth/index.ts` — чисто, включая `eslint-boundaries` (импорты `LoginScreenView.tsx` — только `react` и `@/shared/ui/*`; `index.ts` реэкспортирует из `./ui/LoginScreenView` и `@/shared/ui/ProviderButton`).
- `npx prettier --check` на обоих файлах — чисто.
- **`make check-fe` (tsc + eslint + prettier по всему репозиторию) — полностью зелёный** на момент сдачи фазы: ранее падавшее чужое форматирование (`stores/stream-store.ts`, трек T2) к этому моменту уже почищено параллельным агентом.
- `make build-fe` проходит (`vite build`, tsc-этап включён в `build`-скрипт) — `LoginScreenView` стал первым реальным потребителем `AuthLayout`/`ProviderButton`, вся цепочка трека компилируется целиком впервые.
- `make test-fe` — 13 упавших тестов в 6 файлах, ни один не в скоупе T6: `app/router.test.tsx` (T4), `features/model-selector/ui/ModelSelector.test.tsx` (T3), `pages/artifacts/ui/ArtifactList.test.tsx` (T4), `pages/chat/ui/ChatThread.test.tsx` (T2), `pages/project-chats/ui/ChatList.test.tsx` (T2/T4), `pages/sphere/ui/SphereView.test.tsx` (T4) — все принадлежат другим трекам, идущим параллельно в общей ветке; у `LoginScreenView.tsx` своего теста ещё нет (пишет `test-author`).
- Грепом по слайсу: ни одного упоминания `shared/api`, `stores`, `react-router`, `useQuery`, `useNavigate`; VK встречается только в JSDoc, констатирующем его отсутствие («VK ID не существует ни в каком виде») — тем же паттерном, что уже применён в `ProviderButton.tsx` (T6.1).
- `git status` — diff ограничен `features/auth/ui/LoginScreenView.tsx` и `features/auth/index.ts` (новые); `AuthGate.tsx`, `router.tsx`, `pages/**`, файлы других треков не тронуты.

**T6.4 (живая сверка, постоянных изменений кода нет — обвязка удалена):**

- `npx tsc -b --noEmit` — 0 ошибок по всему проекту, включая все четыре файла трека.
- `npx eslint` и `npx prettier --check` на всех четырёх файлах трека (`AuthLayout.tsx`, `ProviderButton.tsx`, `LoginScreenView.tsx`, `index.ts`) — чисто.
- `npx vite build` (полная прод-сборка) — `✓ built in 52.93s`, без ошибок; впервые прогнана после того, как `AuthLayout` стал реальным потребителем ассета сцены через живой рендер (не только tsc-проверку типов).
- `git status --porcelain` в корне репозитория после уборки обвязки — без единого файла этой фазы; diff вне T6 принадлежит исключительно параллельным трекам T2/T3/T4 (не трогал).
- Полный `make check-fe`/`make test-fe` по всей ветке на момент сдачи T6.4 не прогонялся отдельно от точечных проверок выше — общий гейт остаётся под влиянием параллельных T2/T3/T4 (см. пояснения T6.1–T6.3 выше), а по файлам трека T6 все проверки зелёные.

## Follow-ups

- Ничего вне скоупа фазы не найдено.

## SOFA-посты (id / применил / результат)
