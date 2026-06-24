# Тестирование фронтенда — теория и выбор стека

> Учебный черновик к feat-009. Аудитория — архитектор. Цель — единый разбор инструментов и подходов перед тем, как фиксировать конвенции и разворачивать инфраструктуру.

## Исходная точка

Наш фронт (проверено в коде): **React 19 + Vite 7 + TypeScript 5.9**, server-state на **TanStack Query v5**, client-state на **Zustand v5**, раскладка по Feature-Sliced Design. Тестов — **ноль**: ни одной тест-зависимости в `frontend/package.json`, ни конфигов, ни файлов. Это greenfield: ставим инфраструктуру с нуля одним связным набором, миграции легаси нет.

Хорошая новость в том, что статический слой у нас уже работает как gate: `tsc` + ESLint + Prettier гоняются через `make check-fe`. По модели Testing Trophy (см. ниже) это фундамент пирамиды, и он закрыт.

## Раннер: Vitest

Для Vite-проекта в 2025–2026 дефолт — **Vitest**, не Jest. Причина простая: Vitest переиспользует ту же конфигурацию и трансформацию, что и само приложение (один `vite.config`, те же плагины, нативный ESM + TS), — не нужен отдельный babel/ts-jest пайплайн, который у Jest всегда источник рассинхрона с реальной сборкой. API почти полностью Jest-совместимое (`describe` / `it` / `expect`), отличия косметические: глобальный `vi` вместо `jest` плюс несколько vitest-специфичных хелперов.

### DOM-окружение

Тесты компонентов гоняются в node, поэтому нужен эмулятор браузерного DOM:

| Окружение | Скорость | Полнота API | Когда брать |
|-----------|----------|-------------|-------------|
| **jsdom** | медленнее | выше, спец-комплаентнее | **дефолт** — меньше сюрпризов на краевых случаях |
| happy-dom | быстрее | ниже | если упрёмся в скорость на большом наборе |

Рекомендация — jsdom по умолчанию, happy-dom только при доказанной проблеме со скоростью. Поверх — `@testing-library/jest-dom` для матчеров (`toBeInTheDocument` и пр.); он по-прежнему полезен с Vitest.

## Компонентные тесты: React Testing Library

Базовый принцип RTL — **тестируем поведение, видимое пользователю, а не внутренности компонента**. Чем больше тест похож на то, как софт реально используется, тем больше уверенности он даёт.

Конкретика (гайды Kent C. Dodds / testing-library):

- **Приоритет запросов:** `getByRole` (с `name`) → `getByLabelText` → `getByText`; `getByTestId` — последнее средство, когда по-человечески элемент не достать.
- Всегда через `screen.*`, не деструктуризация из `render`.
- Взаимодействия через `@testing-library/user-event` (реалистичная цепочка событий: focus → keydown → input → ...), а не голый `fireEvent`.
- Асинхронность через `findBy*` / `waitFor`, не ручные таймеры.

Чего **избегать** (всё это — привязка к реализации, ведёт к хрупким тестам):

- лезть в `container.querySelector` / по `className`;
- shallow-рендеринг;
- проверки «вызвалась ли такая-то функция / поменялся ли внутренний стейт»;
- тестирование приватных хелперов в обход публичного контракта.

Диагностический признак привязки к реализации: тест падает при рефакторинге, который не менял наблюдаемое поведение.

## Server-state: TanStack Query v5

Главный источник флаки в тестах на Query — общий кэш между тестами и дефолтные ретраи. Правила (TkDodo, официальный testing-гайд):

- **Новый `QueryClient` на каждый тест** + обёртка `QueryClientProvider`. Полная изоляция, никакого общего кэша — иначе флаки при параллельном прогоне.
- **`retry: false`** в `defaultOptions.queries`. Иначе дефолтные 3 ретрая с exp-backoff превращают тесты на ошибочные запросы в таймауты. Точечные настройки — через `queryClient.setQueryDefaults`, не на самом `useQuery`.
- Хуки тестируем `renderHook` (из `@testing-library/react`) + `waitFor`.
- **v5-нюанс:** `logger` / `setLogger` в v5 **удалён**. В v4 советовали глушить логгер в тестах — для нас неактуально, ошибки в консоль по умолчанию не спамятся.

Практический вывод: заводим тонкую утилиту `renderWithProviders`, которая оборачивает рендер в свежий `QueryClient` с `retry:false` + нужные провайдеры. Все integration-тесты фич идут через неё.

## Client-state: Zustand v5

Zustand-сторы — это **module-level синглтоны**, поэтому их состояние **протекает между тестами** и его обязательно сбрасывать.

> Отмечу расхождение с нашим hard-rule «никаких module-level синглтонов»: Zustand-сторы формально таковыми и являются. Это известное архитектурное отступление фронта; тест-сброс как раз закрывает связанный с ним риск утечки состояния — то есть тестирование здесь не борется с конвенцией, а страхует её слабое место.

Официальный гайд Zustand даёт аккуратный паттерн вместо ручного `setState`: файл `__mocks__/zustand.ts` оборачивает `create`, копит reset-функции всех сторов, а `afterEach` откатывает каждый стор к `store.getInitialState()`. Один раз настроили — дальше сброс автоматический для всех сторов.

## Мокинг API: MSW

Стандарт мокинга сети в 2025–2026 — **Mock Service Worker (MSW)**. Он перехватывает запросы на **сетевом уровне** (Service Worker в браузере / `setupServer` в node), поэтому код приложения не знает, что отвечает мок: не нужно подменять внутренности `fetch` / `axios`. Один набор хендлеров переиспользуется в unit/integration-тестах, Storybook и dev-режиме.

Жизненный цикл в Vitest:

```
beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())
```

**MSW против ручных моков `fetch`:** ручные моки хрупкие, привязаны к реализации HTTP-клиента и легко рассинхронизируются с реальным контрактом; MSW даёт реалистичный контракт на границе. Цена — разовая настройка на пару часов.

### SSE-стрим агента — ключевой кейс для нас

У MSW теперь **first-class поддержка Server-Sent Events** (`mswjs.io/docs/sse/`): раньше стрим эмулировали вручную через `ReadableStream` + `text/event-stream`, теперь есть штатный API для эмиссии событий. Это напрямую закрывает мокинг стримящихся ответов агента от бэкенда — самый нетривиальный кусок нашего фронта с точки зрения тестов.

Нюанс на стороне приложения: нативный `EventSource` не умеет передавать заголовки авторизации, поэтому стрим с авторизацией часто делают через `@microsoft/fetch-event-source`. Подход к мокингу с ним тоже работает — это влияет на форму клиента, не на стратегию теста.

## E2E: Playwright

State of JS 2025 (опубликован янв. 2026): удовлетворённость **Playwright ~91%** против **Cypress ~72%** — рекордный разрыв; Playwright обогнал Cypress и по использованию. Плюсы: настоящий мульти-браузер (Chromium / Firefox / WebKit), параллелизм, скорость, бесплатность, авто-ожидания, codegen и trace viewer.

Для нового проекта в 2026, где нет легаси-экспертизы в Cypress, дефолт — **Playwright**. E2E держим **тонким слоем**: 3–7 сценариев на критичные сквозные потоки (логин + refresh-токен, основной learning-flow со стримом агента). Покрывать e2e большинство фич — анти-паттерн (дорого, медленно, флакоёмко); логику фич закрываем integration-тестами с MSW.

## Стратегия: Testing Trophy

Модель Kent C. Dodds, снизу вверх:

```
        ╱ e2e ╲          немного — критичные journey (Playwright)
      ╱integration╲      ОСНОВНОЙ ОБЪЁМ — компонент + хуки + MSW
     ╱    unit     ╲     точечно — чистая логика, хуки, сторы
    ╱─── static ───╲     фундамент — tsc + ESLint (уже gate)
```

Девиз — «Write tests. Not too many. Mostly integration». Основную ценность даёт **integration**: компонент вместе со своими хуками и замоканной через MSW сетью — лучший ROI (уверенность на единицу усилий). ROI = confidence / time.

- **Снапшоты — осторожно.** Крупные снапшоты хрупкие и низкоценные, дают ложную уверенность. Допустимы только мелкие, осмысленные.
- **Coverage — ориентир, не цель.** Не гнаться за 100%; мёртвый процент бесполезен. Полезнее смотреть, что именно не покрыто, и держать тренд.

## Раскладка тестов и FSD

FSD не диктует расположение тестов; сложившаяся практика — **колокация рядом со слайсом/сегментом**: `Button.tsx` ↔ `Button.test.tsx`, тест хука рядом с хуком в его сегменте. Это держит тест и код в одном месте и переживает перемещения слайсов.

**E2E живут отдельно** (top-level `e2e/` или `tests/`): они кросс-слайсовые, про пользовательские сценарии, а не про юнит FSD.

## Рекомендуемый минимальный стек

Один связный набор, ставится за один заход:

- **Vitest** + **jsdom** + `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`.
- **MSW** (`setupServer` для node-тестов) — единый источник моков API, включая SSE-стрим агента.
- Тонкие тест-утилиты: `renderWithProviders` (свежий `QueryClient` с `retry:false` + провайдеры) и `__mocks__/zustand.ts` для авто-сброса сторов в `afterEach`.
- **Playwright** — тонкий слой e2e на критичные happy-path.
- `vitest.setup.ts`: подключение `jest-dom`, старт/сброс MSW-сервера, глобальный `afterEach(cleanup)`.
- Наш `logger` (`@/shared/lib/logger`) — мокать в setup, чтобы тесты не шумели и можно было ассертить логирование при нужде.
- Цели Makefile: `make test-fe` / `make test-fe-watch` / `make e2e` (Makefile — канонический интерфейс проекта).

Объём по приоритету: львиная доля — **integration** фич (`features/*`) с MSW; точечные **unit** — на чистую логику/хелперы в `shared` и нетривиальные хуки/сторы; **минимум e2e** на сквозные потоки.

## Развилки для архитектора

1. **Конфигурация Vitest.** Отдельный `vitest.config.ts` (рекомендую) vs секция `test` прямо в `vite.config.ts`. Внутренняя развилка — **globals on/off**: `globals:true` даёт Jest-подобный DX, но добавляет глобалы; `globals:false` + явные импорты чище и ближе к нашим hard-rules про явность.
2. **DOM:** jsdom (рекомендую) vs happy-dom (скорость — только при доказанной проблеме).
3. **Мокинг API:** MSW (рекомендую) vs ручные `vi.fn()`-моки (разумны только для 2–3 тривиальных тестов на старте; долгосрочно — MSW, особенно из-за SSE).
4. **E2E-стек:** Playwright (рекомендую) vs Cypress (только при наличии экспертизы — у нас её нет).
5. **Объём e2e:** минимальный 3–7 сценариев (рекомендую) vs расширенное покрытие (анти-паттерн Trophy).
6. **Раскладка тестов:** колокация в слайсах (рекомендую, по FSD-практике) vs отдельный top-level `tests/`. E2E в любом случае top-level.

## Что это значит для нас

- Стек ставится с нуля **одним набором** — нет легаси, можно сразу взять современный канон.
- Три проектных акцента, которые нельзя упустить при настройке инфраструктуры:
  1. **SSE-мокинг агента** через нативный MSW SSE — самый нетривиальный кусок, но инструмент под него уже есть.
  2. **Обязательный сброс Zustand-сторов** между тестами (`__mocks__/zustand.ts`) — наши сторы module-level, без сброса будет протечка состояния и флаки.
  3. **Свежий `QueryClient` + `retry:false`** на каждый тест для TanStack Query v5 (и помним: `setLogger` в v5 удалён).
- Центр тяжести — **integration с MSW**, не unit и не e2e. Static-слой (tsc/ESLint) уже закрыт нашим gate.
- Финальная конфигурация (развилки выше) и цели Makefile — инфраструктурное решение, не выводимое однозначно из текущей документации, поэтому согласуется с архитектором.

## Источники

- Vitest vs Jest / DOM: https://www.speakeasy.com/blog/vitest-vs-jest · https://tech-insider.org/vitest-vs-jest-2026/ · https://blog.incubyte.co/blog/vitest-react-testing-library-guide/ · https://www.reddit.com/r/reactjs/comments/1fiasoc/should_you_still_use_jestdom_with_vitest/
- React Testing Library: https://kentcdodds.com/blog/common-mistakes-with-react-testing-library · https://testing-library.com/docs/react-testing-library/intro/ · https://dev.to/tahamjp/react-component-testing-best-practices-for-2025-2674
- TanStack Query testing: https://tkdodo.eu/blog/testing-react-query · https://tanstack.com/query/latest/docs/framework/react/guides/testing · https://github.com/TanStack/query/discussions/1090
- Zustand testing: https://zustand.docs.pmnd.rs/learn/guides/testing · https://github.com/pmndrs/zustand/issues/242
- MSW (+ SSE): https://mswjs.io/docs/quick-start/ · https://mswjs.io/docs/sse/ · https://mswjs.io/blog/server-sent-events-are-here/ · https://alexocallaghan.com/mock-sse-with-msw · https://stevekinney.com/courses/testing/testing-with-mock-service-worker
- E2E Playwright vs Cypress (2025–2026): https://tech-insider.org/playwright-vs-cypress-vs-selenium-2026/ · https://getautonoma.com/blog/e2e-testing-tools · https://maestro.dev/insights/top-5-end-to-end-testing-frameworks-compared
- Стратегия / Testing Trophy: https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications · https://kentcdodds.com/blog/write-tests · https://kentcdodds.com/blog/static-vs-unit-vs-integration-vs-e2e-tests
- FSD + тесты: https://fsd.how/docs/get-started/overview/
