# Findings — Services + DB (main app)

Scope: `backend/app/services/`, репозитории, DB-session lifecycle (`get_db_session`), service-side вызовы инфры.

---

### [F-SVC-01] TOCTOU при регистрации → сырой IntegrityError вместо доменного отказа 🟡
- Локация: `backend/app/services/auth.py:37-45` (модель `models/user.py:23`, name unique=True)
- Правило: №4, №2
- Текущее: `get_by_name` → проверка → `create` (flush может бросить IntegrityError). Check-then-act гонка; второй параллельный запрос ловит unique-violation на flush. `IntegrityError` всплывает мимо доменной трансляции (глобального хендлера нет) → 500 вместо 409.
- Направление: ловить IntegrityError на unique → транслировать в `UsernameAlreadyExistsError`; проверку оставить быстрым happy-path.

### [F-SVC-02] Сервисы бросают `fastapi.HTTPException` напрямую — обход доменного барьера, неконсистентно 🟡
- Локация: `services/sphere.py:131`, `services/user_memory.py:71`, `services/mcp_server.py:266,271,317,353,371,388,399`
- Правило: №3, №4, №7
- Текущее: эти сервисы кодируют HTTP-статусы внутри доменной логики (`raise HTTPException(422, ...)`), тогда как `project.py`/`chat.py`/`artifact.py`/`auth.py` бросают доменные исключения и полагаются на барьер. Две несовместимые модели в одном слое.
- Направление: выбрать одну. Каноничнее — сервис бросает доменное исключение, маппинг в статус — единый хендлер на барьере. **Центральная ось feat-007.**

### [F-SVC-03] `_fetch_or_503`: широкий except, потеря причины (`from None`), сырой str(exc) клиенту 🟡
- Локация: `services/mcp_server.py:267-274`
- Правило: №7, №4
- Текущее: `except Exception as exc: logger.warning(..., error=str(exc)); raise HTTPException(503, detail={"reason": str(exc)}) from None`
- Проблема: (1) `from None` рвёт цепочку — оператор теряет исходное исключение; (2) лог без exc_info; (3) `str(exc)` уходит клиенту в detail.reason — утечка.
- Направление: `from exc`, `exc_info=True`, клиенту стабильный код без сырого str(exc).

### [F-SVC-04] `MCPToolResolver.resolve`: внешний `except Exception → tools=[]` маскирует сбой БД 🟡
- Локация: `services/mcp_tool_resolver.py:63-70` (внутренний per-server catch — `:103-118`)
- Правило: №3, №5
- Текущее: внешний `except Exception → tools=[]` (с exc_info) накрывает и обращения к БД (`repo.list_by_*`, строки 78-88), хотя per-server degrade уже есть внутри. Сбой БД молча → «нет MCP-инструментов» (silent degradation критичного пути).
- Направление: сузить/убрать внешний catch, опираясь на per-server degrade; инфра-сбой БД должен всплывать.

### [F-SVC-10] `validate_url`: DNS-сбой и «приватный IP» схлопнуты в один ValueError → один статус 🟢
- Локация: `services/url_validator.py:35-47`; маппинг `mcp_server.py:265-266,352-353,387-388`
- Правило: №2/№4
- Текущее: `socket.gaierror`→ValueError (с `from e` — ок) и «резолвится в приватный IP» (SSRF policy) — оба ValueError → оба в HTTPException(400). Клиент не отличает «несуществующий домен» от «попытка SSRF». (Вне рубрики: `getaddrinfo` синхронный — блокирует event loop.)
- Направление: развести два понятия разными типами/статусами либо задокументировать слияние.

### [F-SVC-11] `EncryptionService.decrypt`: сырой `InvalidToken` от Fernet всплывает без трансляции 🟢
- Локация: `services/encryption.py:32-37` (вызов `mcp_server.py:237`, `mcp_tool_resolver.py:147`)
- Правило: №4, №2
- Текущее: при битом/несовместимом ciphertext `Fernet.decrypt` бросает `cryptography.fernet.InvalidToken` сырым; в `mcp_tool_resolver` его проглотит широкий catch (F-SVC-04) → сервер молча «пропадёт».
- Направление: транслировать в доменное `EncryptionError` с логом.

---

## Хорошие примеры

- **[F-SVC-05] ✅ get_db_session** (`api/deps.py:49-58`) — yield-dependency: commit на чистом выходе, `except: rollback + raise`, `finally: close`. Эталон секции «транзакции».
- **[F-SVC-06] ✅ commit до raise** (`services/auth.py:70-75`, ср. `chat.py:54-56`) — ревокация сессий при replay обязана пережить исключение; явный commit перед `raise ReplayDetectedError` + комментарий «почему».
- **[F-SVC-07] ✅ degrade некритичной observability** (`chat.py:82-100,166-191`) — Redis trace_ids/feedback некритичны → широкий except + exc_info + fallback. Контраст к F-SVC-04 (там критичный путь).
- **[F-SVC-08] ✅ verify_password** (`services/security.py:19-23`) — `except VerifyMismatchError: return False`; прочие ошибки argon2 всплывают. «Рутинная ветка → значение», узкий тип.
- **[F-SVC-09] ✅ Optional на чтении → доменное исключение на решении** — репозитории возвращают None (`thread_view.py:23`, `project.py:21`, `artifact.py:35`, `user.py:15`, `refresh_token.py:21`), сервисы поднимают `EntityNotFoundError` на точке решения (`project.py:24-28`, `artifact.py:14-18`, `chat.py:73-76,135-137`).

---

## Итог
11 findings: 4 🟡, 2 🟢, 5 ✅.
Топ-3: F-SVC-02 (неконсистентная трансляция в слое сервисов — центральная ось), F-SVC-01 (TOCTOU IntegrityError → 500 вместо 409), F-SVC-04 (широкий except маскирует сбой БД).
