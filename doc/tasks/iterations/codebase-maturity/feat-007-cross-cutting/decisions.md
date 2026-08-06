# feat-007 — Принятые архитектурные решения

Зафиксировано с архитектором по итогам аудита (`audit-findings.md`). Это основа для конвенций (`conventions.md`) и refactor-плана.

## D-ERR-1 — Модель ошибок: канон путь A + доменная иерархия AppError
Сервисы НЕ знают про HTTP-транспорт. Бросают доменные исключения; маппинг в статус — единый барьер.
- Завести иерархию `AppError` (база несёт `code` + дефолтный `status`, не знает про HTTP): `NotFoundError`(404), `ConflictError`(409, unique/лимит), `SecurityPolicyViolationError`(422), `UpstreamUnavailableError`(503) и т.д.
- Один exception-handler разворачивает `AppError` → problem+json (вместо россыпи `@app.exception_handler` и прямых `HTTPException` в сервисах).
- **Объём: ПОЛНЫЙ рефактор в feat-007** — путь B (`sphere`, `user_memory`, `mcp_server`, прямые `HTTPException` в сервисах) переводится на путь A. Распараллелить сабагентами.

## D-ERR-2 — Барьерный стек (3 слоя на границе приложения, оба сервиса)
1. `AppError` → 4xx/409/422 problem+json (доменное).
2. Инфра-исключения (`OperationalError`/`DBAPIError`→503, timeout→504) → problem+json + лог `exc_info`.
3. generic `Exception` (last-resort) → 500 problem+json без внутренностей + лог `exc_info`.
Закрывает T1 (500-gap) и T2 (нет трансляции). Синхронно в `backend/app/api/problem.py` и `siem_service/api/problem.py`.

## D-ERR-3 — Карта «источник → статус»
NotFoundError→404; ConflictError(unique/лимит)→409; SecurityPolicyViolationError→422; валидация→422; OperationalError/DBAPIError→503; внешний инструмент↓(wkhtmltopdf/MCP)→502/503; timeout→504; необработанное→500.
Точечно: IntegrityError(unique) в регистрации юзера и в имени SIEM-правила → 409 (а не 500).

## D-ERR-4 — Result/Either НЕ вводим
Дефолт: исключения + Optional. «Результат-как-значение» через Pydantic-модель — только для ожидаемого доменного исхода, по которому ветвится непосредственный вызывающий (уже применяется: MCP test-connection, classifier). Никаких сторонних Result-библиотек.
Эталоны в конвенции: Optional на чтении → доменное исключение на точке решения (F-SVC-09); узкий catch «рутинная ветка → значение» (verify_password, F-SVC-08).

## D-ERR-5 — Tools error handling: уточнено эмпирикой (ОЖИДАЕТ АПРУВА)
Изначально: store is None → fail-fast `RuntimeError`, агент не продолжает без памяти. Эмпирика (`empirical-reentry-toolnode.md`) показала, что текущий механизм fail-fast (сырой `RuntimeError` из tools наружу) **навсегда ломает thread**: остаётся висячий `AIMessage(tool_calls)` без `ToolMessage` → следующий вход даёт невалидную OpenAI-историю → 400. Это широкий корректностный баг: ЛЮБОЕ не-`ToolInvocationError` в tools (транзиент стора, падение MCP-tool, баг) бьёт так же.

Уточнённая модель (две развязанные заботы):
- **Core-зависимость → fail-fast в `agent_node`** (`graph.py:225-226`, остаётся). Полное отсутствие стора падает ЗДЕСЬ, ДО генерации tool_calls → сироты нет, история валидна. Это и есть настоящий «агент не работает без стора».
- **Tool-level отказы → `ToolNode(tools, handle_tool_errors=True)`** (`graph.py:339`). Исключение в tool → `ToolMessage(status="error")`, ReAct-шаг закрывается, thread остаётся валидным, агент реагирует. Узкое окно store-is-None на записи, транзиенты, баги tools — больше не бьют thread. Операторская наблюдаемость сохраняется через лог `exc_info` + метрику (агент продолжает на уровне thread, но это НЕ молча).
- **Репарация уже испорченных threads:** утилита на входе (`runner.py`/`CheckpointHistory`) синтезирует `ToolMessage(error)` для висячих tool_calls. `handle_tool_errors` старые сироты не чинит.
- Контраст (без изменений): секция не найдена при существующем сторе → graceful строка (доменное отсутствие).

**ФИНАЛ (апрув получен):**
- `ToolNode(tools, handle_tool_errors=True)` — принято. Это штатный механизм LangGraph (фреймворк проектировал именно его под этот случай), не воркэраунд. Любое исключение в tool → error-`ToolMessage`, ReAct-шаг закрывается, thread валиден.
- Core fail-fast в `agent_node` остаётся; отдельную проверку `store is None` в tools специально не выделяем — она просто станет error-`ToolMessage`, как любое другое исключение.
- **Репарацию уже сломанных тредов НЕ делаем** (архитектор: пред/постобработкой заниматься не хочется). Принятое следствие: треды, уже окирпиченные до фикса (если такие есть в проде — окно узкое, транзиентные сбои), останутся невалидными; новые защищены. Если когда-нибудь всплывёт — репарация-утилита добавляется отдельно (дёшево). Кандидат в known-issues.
- Наблюдаемость инфра-класса tool-ошибок: лог `exc_info` + метрика (агент продолжает на уровне thread, но не молча).
Корректностный баг — чиним в feat-007.

## D-ERR-6 — Guard fail-open: обе дороги наблюдаемы (D1)
Свести обе дороги деградации в CLEAN к ОДНОМУ наблюдаемому сигналу `GRACEFUL_DEGRADATION`:
- Дорога 1 (LLM-исключение, guard.py:143) — уже наблюдаема.
- Дорога 2 (исчерпание ретраев классификатора, classifier.py:125) — сделать наблюдаемой (security-event + метрика), сейчас тихая.
- Завести ОТДЕЛЬНЫЙ канонический `event_type` для деградации (напр. `AGENT_GUARD_DEGRADED`) — не переиспользовать injection-событие.
- Направление (INPUT/OUTPUT) выбирать по checkpoint, не зашивать константой.

## D-ERR-7 — SIEM потеря событий (Вариант 1), чиним в feat-007
Разделить барьеры в `subscriber.py`: `ValidationError`(poison) → drop + XACK (как сейчас); транзиентный инфра-сбой (`OperationalError`) → **НЕ XACK** (оставить в PEL, `_read_pending` переобработает) + bounded-счётчик попыток, чтобы не зациклить. Dead-letter — overkill, в refactor-список.

## D-ERR-8 — Frontend (обвязка сейчас, дизайн отдельно)
В feat-007: общий парсер problem+json в `shared/lib` (обобщить `security-error.ts` на detail/title/категорию) + дефолты `QueryClient` (не ретраить 4xx, рассмотреть глобальный onError) + конвенции (включая язык сообщений — продукт русский).
Отдельно (карточка во frontend-тасклист): тост/баннер-система + редизайн error-UI states. Это новый UI-объём, не cross-cutting.

## D-ERR-9 — Таймауты (финал)
Механика: Redis `socket_timeout`/`socket_connect_timeout`; Postgres `statement_timeout` (**120s**, на отдельный SQL — не на turn агента); LangGraph checkpointer/store; MCP builder (единый таймаут); frontend axios `timeout`.
LLM:
- Основной чат — **НЕ трогаем** (reasoning-модели думают 10+ мин; openai-дефолт 600s оставляем).
- Guard-классификатор — **45s** (на таймауте → наблюдаемая деградация в CLEAN по D-ERR-6, выбор в пользу UX; принятый риск — теоретический таймаут-абьюз).
- Суммаризация — **5 мин**.
- `max_retries` = **2** для всех управляемых нами вызовов.

## D-ERR-11 — Где конфигурируем числа: Settings/env, не хардкод
Все таймауты и `max_retries` — операционные настройки → `Settings(BaseSettings)` (env-переменные), не константы в коде (хард-правило проекта «Env vs константы»). Добавление каждой env-переменной = одновременная правка `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml`. `MCP_TIMEOUT` (сейчас константа) — промотировать в Settings для единообразия. Состав новых env: guard/summarizer LLM timeout, LLM max_retries, Redis socket/connect timeout, DB statement_timeout, MCP timeout, frontend axios timeout (через `VITE_`). Основной чат-LLM timeout — пока не вводим (не трогаем).

## D-ERR-10 — Scope feat-007
Делаем здесь ВСЁ перечисленное (D-ERR-1…9), включая полный рефактор путь B→A и SIEM-фикс. ЕДИНСТВЕННОЕ исключение — тост-система + редизайн error-UI (→ frontend-тасклист, отдельной карточкой).

## Закрытые микро-вопросы
- Re-entry после исключения в tool → эмпирика подтвердила баг (висячий tool_call); фикс — D-ERR-5 финал (`handle_tool_errors=True`, без репарации).
- `max_retries` = 2 (D-ERR-9).
- Конфигурирование чисел → Settings/env (D-ERR-11).
- `statement_timeout` = 120s; на отдельный SQL, не на turn. Проверить при реализации, что не держим открытую транзакцию вокруг LLM-вызова (если держим — отдельная находка).
- Карточка тостов → добавлена в `doc/backlog.md` (Frontend / UX, P2), коммит в develop.

## Резолюции Open Questions (после планирования)
- **OQ-A** `handle_tool_errors` → **callable** (логирует `exc_info` + возвращает безопасный текст в `ToolMessage(status="error")`). Уточняет D-ERR-5 (буквальное `=True` отвергнуто — гасит молча).
- **OQ-B** «метрика» деградации guard = канал `security_event` (SIEM считает/алертит) + `logger.error`. **Отдельный счётчик не вводим** (нет metrics-инфры).
- **OQ-C** siem — **полное зеркало** main app: своя иерархия `AppError` (свой `exceptions.py`) + барьер 3 слоя + роуты на доменные исключения. Для консистентности и роста сервиса; общий пакет исключений НЕ заводим (каждый сервис — своя копия). Это расширяет scope T4 и делает T4 зависимым от паттерна T1 (T1 раньше T4).
- **OQ-D** siem Redis: инвариант `socket_timeout > xread_block` (block=1000ms → socket_timeout=5s); отдельный клиент не нужен.
- **OQ-E** bounded-счётчик D-ERR-7: использовать delivery-count PEL Redis Streams, после N (≈5) → drop + `logger.error` с payload; dead-letter не вводим.
- **OQ-F** `VITE_*` документируем в **общем** корневом `.env.example` (единый источник правды), отдельный `frontend/.env.example` НЕ заводим.

## Режим исполнения
**Серийно в одном worktree** (отдельные worktree, в т.ч. эфемерные, ЗАПРЕЩЕНЫ архитектором). Implementer'ам передаётся предупреждение: рабочий каталог общий, при неожиданном состоянии файлов — приостановиться и адаптироваться. Порядок (по зависимостям): **T1 → T4 → T2 → T3 → T5** (T1 — фундамент AppError+барьер; T4 зеркалит паттерн T1; T2 кладёт таймауты на финальные файлы; T3/T5 изолированы). Каждый трек: implement → `make check`/`make check-fe` → тест-кейсы трека → локальный коммит.
