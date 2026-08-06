# Code Review — T5 Frontend (feat-007 cross-cutting error handling)

Ревьюер: code-reviewer (frontend-домен). Скоуп: `git diff develop...HEAD -- frontend` + сопутствующая env-документация `VITE_*`.
Гейт `make check-fe` (tsc + ESLint + Prettier) прогнан локально — **зелёный**.

## Summary

Трек T5 реализован близко к плану `plan-T5.md` и решениям D-ERR-8/9/11. Все целевые требования выполнены:

- **Парсер `api-error.ts`** читает problem+json по приоритету `detail → title → категория по статусу`, без `any` (узкий type-guard `isProblemBody` по образцу `security-error.ts`), edge-cases (нет `response`, `ECONNABORTED`, не-`AxiosError`, тело не-JSON, пустой `detail`) покрыты. Сырьё (`error.message`, `HTTP <status>`) пользователю **не** уходит — проверено grep'ом по всему `frontend/src`: остаётся только в комментарии-инварианте парсера.
- **axios `timeout`** из `VITE_API_TIMEOUT_MS` на обоих клиентах (`apiClient`, `siemClient`).
- **QueryClient** не ретраит 4xx (`shouldRetryQuery`), мутации `retry: false`, bounded-ретрай 5xx/сеть (`< 2`, согласован с backend `max_retries=2`).
- **Логирование** только через `@/shared/lib/logger`; новых `console.*` нет.
- **FSD**: парсер в `shared/lib`, импорт по файлу (`@/shared/lib/api-error`), публичные API слайсов не нарушены, barrel не заведён.
- **Русский язык** во всех сообщениях; новых зависимостей и тостов нет (вне scope корректно соблюдён).
- **SSE**: защита `JSON.parse` кадра не глотает молча (`logger.warn` + `continue`), битый кадр не роняет стрим; first-byte timeout с откатом; `getProblemMessageFromBody` в fetch-ветке вместо `HTTP <status>`.
- **Откат оптимистичного лайка** в `FeedbackButtons` корректен (`prevFeedback` снимается до апдейта, восстанавливается в `catch`), консистентен с обновлённой § Optimistic в conventions.md.

Блокеров нет. Находки — наблюдаемость логов, одна пропущенная (вне scope) поверхность с тем же дефектом, и пара мелочей по точности именования.

## Находки

| # | Severity | Файл / место | Суть |
|---|----------|--------------|------|
| 1 | nice-to-have | `pages/sphere/ui/SphereEditor.tsx:25,41` | Тот же дефект F-FE-07, что починен в `MCPServerForm`: рендерится только `isSecurityViolation(error)`, все прочие ошибки сохранения (409/422/503/сеть) **молча глотаются** — пользователь жмёт Save, ничего не происходит, фидбэка нет. Аудит (`audit-raw-06`) эту поверхность не отметил, в plan-T5 её нет → формально вне scope трека. Но после фикса MCP-формы появилась несогласованность одного класса ошибки. Кандидат на in-place дрейф-фикс (`: error ? getApiErrorMessage(error) : null`) либо явный перенос в backlog. |
| 2 | nice-to-have | `app/providers/QueryProvider.tsx:38,43` | `QueryCache.onError` / `MutationCache.onError` логируют `getApiErrorMessage(error)` — уже санированную русскую строку, а не объект ошибки. В централизованном (часто единственном для query) хендлере теряются `status`/`url`/стек для диагностики. Лучше логировать саму `error` (или строку + объект), как это делают локальные хендлеры (`logger.error("[Rename project error]", err)`). Конвенцию (logger, не console) не нарушает — это про качество лога. |
| 3 | nice-to-have | мутации с локальным `onError` (`ProjectActions`, `CreateProjectModal`) | Двойное логирование: локальный хендлер (`logger.error(..., err)` со стеком) + глобальный `MutationCache.onError` (friendly-строка). Шум. Зеркально: мутации **без** локального хендлера попадают только в глобальный лог → в логах лишь санированная строка без стека (см. п.2). |
| 4 | nit | `pages/chat/model/useAgentStream.ts:17,73,141` | `FIRST_BYTE_TIMEOUT_MS` и комментарий «first byte received» неточны: таймер снимается на `response.ok` (заголовки ответа), а не на первом байте тела. Поведение **корректно** и намеренно (иначе reasoning-модель, думающая минуты до первого токена, была бы убита на 30s — у основного чата таймаута быть не должно, D-ERR-9), но имя/коммент завышают семантику. По сути это «таймаут установления ответа». Уточнить коммент/имя. |
| 5 | nit | `pages/chat/model/useAgentStream.ts:255` | Пустая ветка `if (timedOut) { /* … */ }` ради комментария. Читается чище как `else if (!timedOut && isCancellingRef.current) { endStream(); }`. Чистая косметика. |
| 6 | nice-to-have | `shared/lib/api-error.ts:25` (`categoryByStatus`) | Нет отдельных категорий для 400 и 429 — оба падают в дефолтный генерик. Для 429 («слишком много запросов») и 400 осмысленнее свои сообщения. Малозначимо: при наличии `detail` от backend категория не используется. |

## Blocker без прецедента

Отсутствуют. Блокеров нет вовсе.
