# План — T5: Frontend error handling (обвязка)

Трек feat-007. Источник: D-ERR-8, D-ERR-9 (frontend axios timeout), D-ERR-11; findings F-FE-*; спека — `conventions.md` § Обработка ошибок → Frontend (строка 349) + § Frontend (FSD-раскладка).

**Scope трека.** Обвязка обработки ошибок на фронте: общий парсер problem+json, дефолты `QueryClient`, axios `timeout`, применение парсера там, где сейчас показывается сырьё. **НЕ в скоупе** (вынесено в backlog как отдельный UI-объём): тост/баннер-система, визуальный редизайн error-states, общий `query-error-state`-компонент (F-FE-12).

**Принцип атомарности.** Парсер (фаза 1) — фундамент; фазы 2–3 (timeout, QueryClient) независимы между собой и от парсера; фаза 4 (применение) зависит от фазы 1; фазы 5–6 — точечные правки SSE/feedback. Фазы можно делать в порядке 1→2→3→4→5→(6)→7→8, либо 2/3 параллельно с 1.

---

## Фаза 1 — Общий парсер problem+json в `shared/lib`

**Цель.** Единая точка чтения RFC 9457: из ошибки достаём человекочитаемое сообщение на русском. Закрывает корень F-FE-03/04/09/13.

**Изменения.**
- Новый файл `frontend/src/shared/lib/api-error.ts`. Экспорт `getApiErrorMessage(error: unknown): string`:
  - `AxiosError` с телом → приоритет `response.data.detail` → `response.data.title` (оба problem+json) → иначе категория по `response.status`.
  - Нет `response` (сеть/таймаут/CORS) → «Сервер недоступен, попробуйте позже» (или «Превышено время ожидания» для `code === "ECONNABORTED"`).
  - Категории по статусу (fallback, когда нет detail/title): 401/403 → «Недостаточно прав / требуется вход»; 404 → «Не найдено»; 409 → «Конфликт: ...»; 422 → «Некорректные данные»; 5xx → «Ошибка сервера, попробуйте позже».
  - Не-`AxiosError` `Error` и неизвестное → общий русский генерик; **никогда** не `error.message`/`«HTTP 500»` наружу.
  - Типобезопасное чтение тела (без `any`): узкий type guard на форму `{ detail?: string; title?: string }`, по образцу `security-error.ts:6-12`.
- `security-error.ts` **не трогаем**: `isSecurityViolation`/`SECURITY_VIOLATION_MESSAGE` — отдельная забота (детект машинного `type`), три существующих потребителя остаются как есть. `api-error.ts` — про извлечение сообщения; разделение концернов, минимум churn.
- FSD: `shared/lib` без barrel, импорт по файлу `@/shared/lib/api-error` (конвенция строка 661).

**Verification.** `make check-fe` (ESLint + Prettier --check). Парсер — чистая функция, отдельных ручных шагов нет (проверяется через фазу 4).

---

## Фаза 2 — axios `timeout` на клиентах (D-ERR-9, D-ERR-11, F-FE-01)

**Цель.** Запрос не висит вечно; по истечении таймаута — осмысленная ошибка (через парсер фазы 1, `ECONNABORTED`).

**Изменения.**
- `frontend/src/shared/api/client.ts`: добавить `timeout` в `axios.create` — значение из `import.meta.env.VITE_API_TIMEOUT_MS` с числовым fallback-дефолтом (по образцу `VITE_API_URL ?? "/api"`).
- `frontend/src/shared/api/security.ts:92` (`siemClient`): тот же `timeout` из той же env-переменной. **Дрейф-фикс**: F-FE-01/D-ERR-9 называют только `apiClient`, но `siemClient` — клиент-близнец с той же проблемой; чиним в рамках трека (CLAUDE.md «исправляй дрейф на месте»).
- Env-переменная `VITE_API_TIMEOUT_MS`: задокументировать (точное место — см. Open Questions: у фронта нет `.env.example`, его нет в `docker-compose.yml`, существующие `VITE_*` нигде не документированы).

**Verification.** `make check-fe`. 👤 Ручная: при недоступном/медленном backend запрос завершается ошибкой по таймауту, а не бесконечным спиннером.

---

## Фаза 3 — Дефолты `QueryClient` (F-FE-02)

**Цель.** Не ретраить 4xx; одна централизованная точка реакции на ошибки.

**Изменения.**
- `frontend/src/app/providers/QueryProvider.tsx`: `new QueryClient({ defaultOptions, queryCache })`:
  - `defaultOptions.queries.retry`: функция-предикат — не ретраить, если `AxiosError` со `status` 4xx; для прочих (5xx/сеть) — bounded (`failureCount < 2`, согласовано с backend `max_retries=2`, D-ERR-9).
  - `defaultOptions.mutations.retry: false` (мутации с побочными эффектами не ретраим — конвенция «retry только идемпотентное»).
  - `QueryCache`/`MutationCache` `onError`: централизованный `logger.error` (`@/shared/lib/logger`) с разобранным сообщением (`getApiErrorMessage`). **Подача пользователю** (тост/баннер) — backlog; здесь onError = только централизованный лог, без UI-канала.

**Verification.** `make check-fe`. 👤 Ручная: 4xx-ответ (например 404/422) в Network-вкладке не повторяется 3×; 5xx — bounded-ретраи.

---

## Фаза 4 — Применить парсер в местах сырого вывода (F-FE-03/04/05/06/07/09)

**Цель.** Везде, где сейчас пользователю показывается `error.message`/`«HTTP <status>»`/«Something went wrong», — сообщение из парсера.

**Изменения по файлам.**
- `pages/security/ui/SecurityRules.tsx`: error-блок `:118` и toggle-catch `:104-108` → `getApiErrorMessage`.
- `pages/security/ui/SecurityAlerts.tsx:68`, `SecurityEvents.tsx:42` → `getApiErrorMessage` (вместо `error.message`/`"Unknown error"`).
- `pages/security/ui/RuleForm.tsx:162-164` (submitError catch) → `getApiErrorMessage`.
- `app/components/AuthGate.tsx:55-73`: заменить семиуровневую `in`-проверку и fallback `"Something went wrong"` на `setError(getApiErrorMessage(err))`; убрать ручной разбор `err.response.data.detail`.
- `app/components/CreateProjectModal.tsx:27-33` (F-FE-05): обернуть `mutateAsync` в try/catch (или перейти на `mutate` с `onError`), показать сообщение парсера в локальном состоянии; модалка не «зависает» при ошибке. **Требует** добавления места под текст ошибки в разметке модалки (инлайн `<p className="text-sm text-destructive">`, без редизайна).
- `app/components/ProjectActions.tsx:48-66` (F-FE-06): добавить `onError` в rename/delete-мутации → инлайн-сообщение парсера в соответствующем диалоге (локальный `useState`). Без тоста.
- `features/mcp-servers/ui/MCPServerForm.tsx:119-121` + `MCPServersSection.tsx:34-47` (F-FE-07): сейчас рендерится только `isSecurityViolation`; добавить вывод `getApiErrorMessage(error)` для не-security ошибок (дубликат/невалидный URL/5xx). Security-ветка остаётся (`SECURITY_VIOLATION_MESSAGE`).
- `pages/chat/model/useAgentStream.ts:102-106` (F-FE-09): при `!response.ok` — прочитать тело (`await response.json()` в try/catch), собрать `AxiosError`-совместимую форму или вызвать вариант парсера, отдать `onError(detail/title)` вместо `` `HTTP ${response.status}` ``. (Парсер фазы 1 работает с `AxiosError`; для fetch-ветки — либо мелкий локальный адаптер «status+body → message» в `api-error.ts`, либо отдельная экспортируемая `getProblemMessageFromBody(status, body)`, которую переиспользует и `getApiErrorMessage`.)

**Verification.** `make check-fe`. 👤 Ручная по каждой поверхности: ошибка показывается осмысленным русским текстом (detail сервера), не сырьём. Минимум: security-страница при 5xx; AuthGate при неверном пароле (RU detail); создание проекта-дубликата; стрим при 4xx/5xx до первого байта.

---

## Фаза 5 — SSE: таймаут на первый байт + защита парса кадра (D-ERR-9 SSE, F-FE-10)

**Цель.** Установление SSE-стрима не висит вечно; битый кадр не роняет весь стрим.

**Изменения.**
- `pages/chat/model/useAgentStream.ts`: **первобайтовый таймаут** — отдельная политика от axios (D-ERR-9: «для SSE — таймаут на первый байт»). Таймер до получения `response`/первого чанка; по истечении — `controller.abort()` + `onError(...)` через парсер. Значение — отдельная env (`VITE_SSE_FIRST_BYTE_TIMEOUT_MS`) либо переиспользование `VITE_API_TIMEOUT_MS` (см. Open Questions). Таймер снимается при первом успешном чтении.
- `useAgentStream.ts:125` (F-FE-10): обернуть `JSON.parse(line.slice(6))` в try/catch — `logger.warn` + `continue` (пропустить кадр), не валить весь стрим. **Оценка: входит как мелкая правка** (3 строки, предотвращает потерю уже полученного текста, изолировано).

**Verification.** `make check-fe`. 👤 Ручная: стрим, который долго не отдаёт первый байт, прерывается по таймауту с сообщением; (опц.) искусственно битый кадр не обрушивает стрим.

---

## Фаза 6 — FeedbackButtons: откат оптимистичного лайка (F-FE-08) [оценка: включить]

**Цель.** При ошибке запроса UI не остаётся рассинхронизированным с сервером.

**Оценка.** Включить как точечную correctness-правку (не UI-редизайн): соответствует конвенции § Optimistic vs пессимистичные («onError восстанавливает снапшот») — это единственная оптимистичная точка в UI. Объём — пара строк.

**Изменения.**
- `pages/chat/ui/FeedbackButtons.tsx:25-35`: запомнить предыдущее значение, в `request.catch` вернуть `setFeedback(prev)` (откат) дополнительно к существующему `logger.warn`.

**Verification.** `make check-fe`. 👤 Ручная: при ошибке feedback-запроса подсветка кнопки откатывается.

> Если архитектор предпочитает держать F-FE-08 в backlog — фаза вырезается без влияния на остальные.

---

## Фаза 7 — Нормализация языка сообщений (F-FE-11)

**Цель.** Сообщения об ошибках — на русском (продукт русскоязычный). Только строки ошибок, без редизайна и без нового компонента (F-FE-12 — backlog).

**Изменения (узко, строки).**
- `app/components/AuthGate.tsx:38,44`: валидационные «Password must be at least 8 characters» / «Passwords do not match» → RU.
- `pages/chat/model/useAgentStream.ts:208,218`: «Connection lost» / «Connection error» → RU (или через парсер).
- `app/components/ErrorBoundary.tsx:37-41`, `pages/chat/ui/ChatView.tsx:67`, `app/components/ProjectList.tsx:15`: EN error-тексты → RU.

> Лейблы UI вне ошибок (заголовки диалогов «Sign In», «New Project», кнопки) — **не** входят в трек (не error-handling). Не трогаем.

**Verification.** `make check-fe`. 👤 Ручная: визуальная проверка RU в перечисленных местах.

---

## Фаза 8 — Сверка конвенций (drift-check)

**Цель.** Убедиться, что `conventions.md` § Обработка ошибок → Frontend (строка 349) соответствует реализации; исправить дрейф, если возник.

**Изменения.** Спека уже описывает целевое поведение (единый парсер `shared/lib`, detail→title→категория, no-retry 4xx, логирование через `@/shared/lib/logger`, русский язык). Правки документа не требуются, **если** не появилось расхождений по ходу. При расхождении (например, в имени/контракте парсера) — поправить формулировку. Env-переменные `VITE_*` — см. Open Questions.

**Verification.** Чтение раздела, сверка с фактическим кодом.

---

## Фаза 9 — Тест-кейсы (отдельная фаза)

**Цель.** Ручной тест-кейс-документ (артефакт итерации) на затронутые поверхности — по конвенции § Тестирование (slice-итерации страхуются ручными тест-кейсами, прогон независимым агентом-тестировщиком).

**Состав (👤 браузерные):**
1. Парсер: 422 с `detail` → показан `detail`; 5xx без `detail` → категорийное RU-сообщение; сетевой обрыв → «Сервер недоступен»; таймаут → «Превышено время ожидания».
2. QueryClient: 4xx не ретраится; 5xx — bounded-ретраи (Network-вкладка).
3. Timeout: недоступный backend → ошибка по таймауту, не вечный спиннер (apiClient и siemClient/security-страницы).
4. Применение: AuthGate (неверный пароль), создание проекта-дубликата, rename/delete конфликт, MCP-форма не-security ошибка, стрим `!ok` до первого байта.
5. SSE: таймаут первого байта; (опц.) битый кадр не роняет стрим.
6. Feedback: откат при ошибке (если фаза 6 включена).

**Verification.** Документ создан; прогон — независимым тестировщиком (вне этого трека).

---

## Файлы трека

Изменяемые / создаваемые:
- `frontend/src/shared/lib/api-error.ts` *(новый)*
- `frontend/src/shared/api/client.ts`
- `frontend/src/shared/api/security.ts`
- `frontend/src/app/providers/QueryProvider.tsx`
- `frontend/src/app/components/AuthGate.tsx`
- `frontend/src/app/components/CreateProjectModal.tsx`
- `frontend/src/app/components/ProjectActions.tsx`
- `frontend/src/app/components/ErrorBoundary.tsx`
- `frontend/src/app/components/ProjectList.tsx`
- `frontend/src/pages/security/ui/SecurityRules.tsx`
- `frontend/src/pages/security/ui/SecurityAlerts.tsx`
- `frontend/src/pages/security/ui/SecurityEvents.tsx`
- `frontend/src/pages/security/ui/RuleForm.tsx`
- `frontend/src/features/mcp-servers/ui/MCPServerForm.tsx`
- `frontend/src/features/mcp-servers/ui/MCPServersSection.tsx`
- `frontend/src/pages/chat/model/useAgentStream.ts`
- `frontend/src/pages/chat/ui/ChatView.tsx`
- `frontend/src/pages/chat/ui/FeedbackButtons.tsx` *(фаза 6, если включена)*
- env-документация `VITE_API_TIMEOUT_MS` / `VITE_SSE_FIRST_BYTE_TIMEOUT_MS` *(место — см. Open Questions)*
- `doc/tech/conventions.md` *(только при обнаружении дрейфа, фаза 8)*

Тест-документ (артефакт итерации) — отдельным файлом в каталоге итерации.

Читаемые (контекст, без правок): `frontend/src/shared/lib/security-error.ts`, `frontend/src/shared/lib/logger.ts`, `frontend/vite.config.ts`, `frontend/src/pages/user-settings/ui/CustomInstructionsSection.tsx`, `frontend/src/pages/sphere/ui/SphereEditor.tsx`.

---

## Open Questions

1. **Где документировать новые `VITE_*` env-переменные.** Хард-правило проекта (CLAUDE.md «Env vs константы», D-ERR-11) требует синхронной правки `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml`. Но это backend-контур: у фронта **нет** `.env.example`, фронт **отсутствует** в `docker-compose.yml`, а существующие `VITE_API_URL`/`VITE_SIEM_API_URL` нигде не задокументированы (только инлайн-fallback в коде). Вопрос архитектору: завести `frontend/.env.example` (и заодно внести туда существующие `VITE_*`), или зафиксировать `VITE_*` иначе? — архитектурно-процессное решение, не беру на себя.
2. **SSE first-byte timeout: своя env или переиспользовать `VITE_API_TIMEOUT_MS`.** D-ERR-9 называет «отдельную политику» для SSE, но конкретного значения/имени переменной не задаёт. Отдельная `VITE_SSE_FIRST_BYTE_TIMEOUT_MS` (семантически чище: первый байт ≠ полный axios-запрос) или один общий таймаут? Влияет на состав env из вопроса 1.
3. **Глобальный `onError` без UI-канала.** Тосты в backlog, поэтому `QueryCache.onError` в фазе 3 — только централизованный лог, без подачи пользователю. Подтвердить, что это и есть ожидаемый объём «рассмотреть глобальный onError» (D-ERR-8), а полноценная подача ждёт тост-итерацию.
4. **F-FE-08 (откат лайка)** — включать в трек (фаза 6, рекомендую) или в backlog? Решение архитектора.

---

## Пересечения с другими треками

Frontend изолирован: трек T5 затрагивает только `frontend/src/**` (+ возможная env-документация). Backend-треки feat-007 (problem+json handlers, доменные исключения, таймауты Redis/PG/MCP/LLM, SIEM pipeline) меняют сервисы и не пересекаются по файлам. Контрактная связь односторонняя: фронт-парсер **читает** форму problem+json (`type`/`title`/`detail`/`status`), которую гарантируют backend-треки (D-ERR-2/3, § REST API) — это контракт, не файловое пересечение. **Пересечений по файлам нет.**
