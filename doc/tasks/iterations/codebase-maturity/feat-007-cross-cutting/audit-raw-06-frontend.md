# Findings — Frontend

Пути относительно `frontend/`. Тостовой/баннерной системы нет вообще (grep `toast|sonner|notification` пуст) — ошибки показываются инлайново или не показываются.

---

### [F-FE-01] Нет HTTP-таймаутов на axios-клиенте 🔴
- Локация: `src/shared/api/client.ts:18-21`
- Правило: №6
- Текущее: `axios.create({ baseURL, withCredentials })` — без `timeout` → запрос висит бесконечно, пользователь видит вечный спиннер. SSE-`fetch` в useAgentStream тоже без таймаута на установление.
- Направление: дефолтный `timeout` на apiClient; для SSE — таймаут на первый байт.

### [F-FE-02] QueryClient без дефолтов: ретраи 4xx + нет глобального onError 🟡
- Локация: `src/app/providers/QueryProvider.tsx:3`
- Правило: №3, №5
- Текущее: `new QueryClient()` без defaultOptions/QueryCache.onError. Дефолт ретраит любую ошибку 3× (включая 4xx). Нет централизованной точки реакции — корень разнобоя F-FE-05…09.
- Направление: `defaultOptions.queries.retry` (не ретраить 4xx); глобальный onError для 5xx/сети.

### [F-FE-03] Security-страницы показывают `error.message` вместо problem+json detail/title 🟡
- Локация: `pages/security/ui/SecurityRules.tsx:118`, `SecurityAlerts.tsx:68`, `SecurityEvents.tsx:42`, `RuleForm.tsx:162-164`
- Правило: №4
- Текущее: `error instanceof Error ? error.message : "Unknown error"` → для axios это «Request failed with status code 500», не detail из problem+json.
- Направление: единый хелпер чтения RFC 9457 (detail → title → сеть/генерик).

### [F-FE-04] Ручное извлечение detail в AuthGate без общего хелпера 🟡
- Локация: `src/app/components/AuthGate.tsx:55-73`
- Правило: №3, №4
- Текущее: семиуровневая `in`-проверка `err.response.data.detail` захардкожена, не переиспользуется (параллельно F-FE-03). Fallback «Something went wrong» в русскоязычном продукте.
- Направление: вынести в `shared/lib` рядом с `security-error.ts`.

### [F-FE-05] `mutateAsync` без catch → unhandled rejection при создании проекта 🟡
- Локация: `src/app/components/CreateProjectModal.tsx:27-33`
- Правило: №2, №7
- Текущее: `await createProject.mutateAsync(...)` без try/catch → при ошибке unhandled rejection, модалка не закрывается, ничего не показано.
- Направление: показать ошибку / `mutate` c onError.

### [F-FE-06] Мутации rename/delete проекта без onError — тихий провал 🟡
- Локация: `src/app/components/ProjectActions.tsx:48-66`
- Правило: №2, №7
- Текущее: только onSuccess; при 409/403/5xx диалог открыт без сообщения.

### [F-FE-07] MCPServerForm показывает только security-ошибку, прочие глотает 🟡
- Локация: `features/mcp-servers/ui/MCPServerForm.tsx:119-121`; `MCPServersSection.tsx:34-47`
- Правило: №2, №4
- Текущее: рендер только если `isSecurityViolation(error)`; дубликат/невалидный URL/5xx не отображаются (нет onError).

### [F-FE-09] Стрим показывает сырой `HTTP <status>` вместо тела ошибки 🟡
- Локация: `src/pages/chat/model/useAgentStream.ts:102-106`
- Правило: №4
- Текущее: `onError(\`HTTP ${response.status}\`)` — тело problem+json игнорируется.
- Направление: при `!response.ok` прочитать JSON, достать detail/title общим хелпером.

### [F-FE-08] Оптимистичный лайк не откатывается при ошибке 🟢
- Локация: `src/pages/chat/ui/FeedbackButtons.tsx:25-35`
- Правило: №5
- Текущее: `setFeedback(next); request.catch(log)` — без отката, рассинхрон UI/сервер.

### [F-FE-10] JSON.parse SSE-кадра без локальной защиты 🟢
- Локация: `src/pages/chat/model/useAgentStream.ts:125`
- Правило: №2
- Текущее: битый кадр → SyntaxError → внешний catch (`:210`) → весь стрим падает, теряя полученный текст.
- Направление: обернуть парс, логировать и пропускать кадр.

### [F-FE-11] Разнобой языка в сообщениях об ошибке 🟡
- Локация: `ErrorBoundary.tsx:37-41`, `ChatView.tsx:67`, `ProjectList.tsx:15`, `useAgentStream.ts:208,218` (EN) vs русские на security-страницах
- Правило: №7
- Направление: зафиксировать язык + словарь стандартных сообщений в конвенциях.

### [F-FE-12] Generic «Failed to load X» игнорирует категорию ошибки 🟢
- Локация: `ChatView.tsx:64-70`, `ProjectList.tsx:13-19`, `ArtifactList.tsx:16`, `ArtifactView.tsx:21`, `SphereView.tsx:22`, `ChatList.tsx:63`
- Правило: №4, №1
- Направление: общий компонент query-error-state (категория → сообщение; 404 может быть empty-state).

---

## Хорошие примеры
- **[F-FE-13] ✅ Хелпер чтения RFC 9457 `type`** (`shared/lib/security-error.ts:6-12`) — централизованный, типобезопасный, читает машинный `type`, переиспользуется в 3 местах. Образец для обобщения на detail/title.
- **[F-FE-14] ✅ Централизованный 401→refresh→retry** (`shared/api/client.ts:50-95`) — single-flight refresh с очередью, повтор запроса, при провале clearToken+reload. Оговорки: reload вместо навигации; второй параллельный путь refresh `ensureFreshToken()` (`:101-129`) для SSE — дубль, кандидат на унификацию.
- **[F-FE-15] ✅ Обработка SSE security_block** (`useAgentStream.ts:168-194`) — оптимистичный патч кэша + инвалидация + замена текста, без транзиентного баннера (persisted-состояние = единый источник правды). «Честный error-state вместо мигающего тоста».

---

## Итог
15 findings: 1 🔴, 8 🟡, 3 🟢, 3 ✅.
Топ-3: F-FE-01 (нет HTTP-таймаутов), F-FE-02 (QueryClient без дефолтов — корень разнобоя), F-FE-03+09 (problem+json не читается; лекарство уже есть — F-FE-13).
Сквозная тема: нет общего канала подачи ошибок (тостов) и нет общего парсера problem+json.
