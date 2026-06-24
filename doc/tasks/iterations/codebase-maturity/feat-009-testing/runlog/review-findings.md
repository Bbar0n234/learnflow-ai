# Ф4 — реестр находок ревью (вход для Ф5)

Сводка adversarial-ревью тестов по скоупам. Ф5 чинит по этому списку: тест-фиксы — на месте;
прод-баги — отдельными фикс-агентами (A6: автор фикса ≠ автор теста); прод-рефакторы и спорные
контракты — эскалация архитектору. Severity: blocker/major/minor.

Легенда владельца фикса: **[test]** правка теста · **[infra]** правка `packages/testing` · **[prod]** баг/рефактор прод-кода (эскалация) · **[doc]** заметка в конвенции.

---

## S6 — Knowledge sphere (45 passed)

- **M1 major [test]+[infra]** `test_sphere_api.py:165`, `test_sphere_service.py:104`: ассерт `reason == "ks_write_rest"` бьёт в fallback-ветку `detection_layer is None`, недостижимую в проде (настоящий guard при INJECTION всегда ставит `detection_layer` → клиент получит `"llm_classifier"`). `StubGuard` с `detection_layer=None` маскирует. Фикс: `StubGuard` уметь проставлять `detection_layer`, ассертить `reason == "llm_classifier"`. Если контракт требует id чекпойнта — это [prod]-баг, решает архитектор.
- **M2 major [test](+[prod] опц.)** Кросс-контракт «агент пишет тулом ↔ REST читает» не покрыт; namespace/key продублированы (сервис `sphere.py:96,146` инлайн vs тулы через `ks_helpers`). Фикс: sociable-тест на общем `InMemoryStore` (тул пишет → сервис видит, и обратно). Опц. [prod]: сервис должен использовать `build_namespace`/`section_key` (дрейф).
- **m3 minor [test]** `test_sphere_service.py:82` namespace-изоляция слабая: не доказано, что проект A реально содержит запись (только пустота B). Добавить ассерт на A.
- **m4 minor [test]** `_parse_markdown_sections` fallback (нет italic-описания) не покрыт — branch-прокол.
- **m5 minor [test]** `_slugify` не проверен на пробелах/спецсимволах (только однословные).
- **m6 minor [test]** тулы драйвятся через `.coroutine`, минуя `.ainvoke`-инъекцию `ToolRuntime` — слепая зона.
- **m7 minor [test]** косметика: лишняя фикстура `store` в двух тестах; `guard.calls` только на truthiness.
- Чисто: ownership-404 (реальный PG), INJECTION→422 skip-write, fuzzy-patch ветки, дубли по правилу, целостность.

## S5 — Chat & streaming (37 passed)

- **B1 blocker [prod]+[test]** ПРОД-БАГ, пользовательский: `messages.py:43` синтезирует terminal-error как `{"type":"error","message":"Stream failed"}`, но контракт (`streaming.md:29`, `runner.py:166`, фронт `useAgentStream.ts:237` читает `event.detail`) требует `detail`. На mid-stream краше фронт получает `onError(undefined)` → пустой toast. Тест `test_message_stream.py:110` закрепил баг (ассертит `message`). Фикс: прод → `detail`; тест → ассертить `detail`. Эскалация архитектору (прод-правка).
- **M1 major [test]** SSE-критпуть на фабрикованном словаре: `FakeAgentRunner` эмитит `type="token"`/`data={content}`, реальный раннер — `text_chunk` (фронт ждёт `text_chunk`); ChatService пробрасывает verbatim → тест зелёный, но пинит несуществующий тип. `text_chunk` не покрыт. Фикс: фейк → продовый словарь (`text_chunk`, error c `detail`, `security_block` c `{checkpoint, detection_layer}`) + контракт-тест на event-vocabulary раннера ↔ ChatService ↔ фронт.
- **M2 major [infra]/[prod] (эскалация)** Фейки `ThreadViewRepository`/`ArtifactRepository`/`TraceStore` — конкретные классы под `# type: ignore`, дрейф сигнатур не ловится (сейчас сверено вручную — совпадает). Фикс: Protocol-интерфейсы для repo/trace_store (как у раннера) ИЛИ вынос фейков в `packages/testing`. Решение об интерфейсах — архитектор.
- **m1 minor [test]** `test_chat_service.py:204` spy на «вызвался `set_message_id`», а не на эффект — fake-with-state + проверка результата.
- **m2 minor [test]** feedback: не ассертится персист в Redis (`store.save_feedback`/delete ключа) — смысл фичи непокрыт.
- **m3 minor [prod?]** `MessageCreate.content: str` без `min_length` → пустой/whitespace ввод даёт 200 (уходит в агента). Тест `test_stream_accepts_empty_content` закрепляет как контракт (A6-тавтология). Вероятно нужен 422. Решение — архитектор; тест не должен enshrine-ить.
- **m4 minor [test]** `security_block` как терминал на HTTP/wire не покрыт (есть только на сервис-слое); порядок «token→error» и сохранность partial не ассертятся по проводу.
- Чисто: Langfuse-mock проверяет полный payload; `cast(TraceStore, FakeRedis)` честный; graceful degradation по результату; ownership 404/403 через реальную цепочку+PG.

## S4 — Projects & artifacts (65 passed, 1 xfailed)

- **[prod] (эскалация)** DELETE проекта не идемпотентен: повторный → 404 вместо 204 (api.md). Зафиксирован `xfail(strict=True)` `test_delete_project_is_idempotent`. Фикс прода → станет xpass. Ревьюер подтвердил xfail корректным инструментом.
- **M1 major [test]** `test_thread_view_repository.py:96` eager-load удовлетворяется identity-map, не `contains_eager` — регрессию не поймает (в проде → lazy-load→MissingGreenlet→500). Фикс: `db_session.expunge_all()` перед `repo.list_recent(...)`.
- **M2 major [test]** `test_thread_view_repository.py:199` «ON DELETE SET NULL» проверяет ORM-UoW-обнуление, не DB-констрейнт (нет `passive_deletes`). Фикс: удалять тред через Core (`sa.delete`) для проверки констрейнта, либо убрать претензию в докстринге.
- **m1 minor [test]** PDF-ветка download (`artifacts.py:73`) не покрыта — покрываема monkeypatch `convert_md_to_pdf` + ручной `app.state.settings`.
- **m2 minor [test]** download ownership-404 (`artifacts.py:66`, дубль guard'а) без теста — добавить аналог `/download`.
- **m3 minor [test]** сервис-list-тесты валидируют фейк, не сервис (§ Антипаттерны) — низкоценны (реальная фильтрация в repo-integration).
- **m4 minor [test]** Content-Disposition имя файла не проверяется; default-формат download не вызван; не проверено, что list-item без `content` (ArtifactListItem); 422 без problem+json тела.
- **m5/nit [scope/test]** каскад project-delete не покрыт; тройка ownership-404 просится в `parametrize`.
- Чисто: транзакционная изоляция/живой PG/per-worker, bulk-UPDATE через expunge, repo ordering/limit/offset, handler ownership+problem+json, целостность.

## S1 — Auth & access (45 passed)

- **M2 major [prod] (эскалация)** ПРОД-БАГ: валидная подпись + битый/отсутствующий `sub` → `uuid.UUID(payload["sub"])` кидает `ValueError`/`KeyError`; `get_current_user` (`deps.py:64`) ловит только jwt-исключения → **500 вместо 401** + утечка стектрейса на auth-критпути. Фикс: тест `jwt.encode({"sub":"not-a-uuid"})`→401 (покраснеет) + прод: ловить `ValueError`/`KeyError` или `options={"require":["sub"]}`, нормализовать в 401.
- **M1 major [test]** Обход logout-теста стоит на НЕВЕРНОЙ диагностике (опровергнута replay-тестом того же набора: незакоммиченный in-session `revoke` ВИДЕН следующему запросу — SQLAlchemy synchronize_session). e2e «register→POST /logout→refresh(R1)→401» писуем и должен существовать. Фикс Ф5: попробовать написать этот e2e (эмпирически разрешить спор), поправить докстринг. ⚠️ Намерение добавить «грань bare-UPDATE» в testing.md — СНЯТО (диагностика была ложной).
- **m1 minor [test]** refresh-тесты не верят выданный access-токен через `/me` (в отличие от login) — токен может быть «непустой, но нерабочий».
- **m2 minor [test]** `test_rate_limit.py:46` переменная `blocked` = на деле `allowed` (инвертирует смысл) — переименовать.
- **m3 minor [test]** rate-limit e2e только на login; register (по IP, 3/3600) и refresh (по IP, 10/60) без e2e-429 — ключи отличаются от login (name+IP).
- Чисто: реальный логин-флоу (без override), негативы access-токена содержательны, replay/ротация настоящие, rate-limit через инъекцию часов (near-pure), encryption round-trip/tamper/disabled, repo наблюдаемый SQL, изоляция лимитера per-app.

## S2 — Agent guard (140 passed)

- **MAJOR-1 [infra] КРОСС-СКОУП** `StubGuard` (`packages/testing/fakes.py:105`) всегда `detection_layer=None` — непредставимо для INJECTION (прод всегда ставит слой: детектор→`hit.layer`, классификатор→`LLM_CLASSIFIER`). Следствие: `block_reason` с непустым слоем и `original_detection_layer` в redaction никогда не исполняются. Фикс: `StubGuard(verdict, detection_layer=...)`. **Закрывает заодно S6 M1.**
- **MAJOR-2 [infra] КРОСС-СКОУП** `StubGuard.calls` пишет только `(content, checkpoint)`, глотает `skip_classifier`/`observe`/`canary_token`. Контракт mid-stream (guard зовётся с `skip_classifier=True, observe=False` на `FINAL_OUTPUT`) не утверждается — рефакторинг уронит, тесты зелёные. Фикс: писать kwargs в `.calls` + тест на mid-stream vs final-output контракт.
- **MINOR-3 [test]** `inspect_in_graph`: ветка `ToolMessage→TOOL_RESULT` не покрыта (только AIMessage→TOOL_CALL_ARG). Параметризовать.
- **MINOR-4 [test]** `SecurityOutcome.reason` нигде не ассертится (следствие MAJOR-1); для `inspect_in_graph` можно уже сейчас (`assert outcome.reason == "llm_classifier"`).
- **MINOR-5/6 [test/infra]** fail-safe observer-тесты только `isinstance`/«не упало» (на грани false-green); мёртвый `except KeyError` в `_safe_direction` фейка.
- Чисто: семантика двух слоёв разведена, деградация classifier через реальные петли, spy на результат не на вызов, реакция-не-качество, A6 (прод security не трогался).

> **Кросс-скоуп фикс-задача Ф5:** обогатить `StubGuard` (param `detection_layer`, запись kwargs в `.calls`) — закрывает S2 MAJOR-1/2/MINOR-4 + S6 M1. Затрагивает frozen `packages/testing` → один фикс-агент, потом обновить потребителей S2/S6.

## S8 — SIEM + contracts (siem 46, contracts 64) — Ф3-отчёт (Ф4-ревью ожидается)

- **[prod] (эскалация)** Баг: не-JSON payload реролит `JSONDecodeError` в supervisor-барьер → crash-loop до terminal-drop, асимметрично с poison-drop для schema-invalid JSON. Тест фиксирует фактическое поведение.
- **[prod] (эскалация)** `_is_known_event_type` — мёртвый код: строгий `EventType` Literal отвергает unknown как poison раньше soft-mode → метрика `siem_unknown_event_type` недостижима.
- **БЛОКЕР [infra] (эскалация)** trace_store НЕ покрыт: на Redis (не PG, как было в строке скоупа), харнессу не хватает Redis-фикстуры, лежит в `backend/tests` вне путей S8. Ф5: добавить Redis-testcontainer фикстуру в `packages/testing` + закрыть trace_store.
- **БЛОКЕР [build/Ф6]** `make test` не собирает `packages/siem-contracts/tests` — внутренний страж «Literal ⇔ constants» только в библиотечных тестах, вне CI-гейта. Ф5/Ф6: добавить цель Makefile, включить в гейт.
- Cross-side контракт сделан AST-сканом исходников эмиттера (т.к. `app` неимпортируем из siem-env) — ревьюеру проверить осмысленность.

### S8 — Ф4-ревью (вернулось)
- **B1 blocker [test]+[prod-рефактор] (эскалация)** Cross-side контракт НОМИНАЛЕН: `test_cross_side_contract.py:59` тавтология (Literal в поле того же Literal), `:74` вакуумный AST-скан (все 7 emission-сайтов через переменные, не строковые литералы → `hardcoded==frozenset()`); `_EMITTER_FILES` неполон (2 из 7: пропущены `graph.py:180,344`, `mcp_server.py:318`, `runtime_security.py:220`, `sphere.py:119`, `user_memory.py:59`). Дрейф «одна сторона добавила тип» не ловится. Фикс: двусторонняя полнота + перенос cross-side в backend-пакет, ИЛИ типизированный `emit_security_event(event_type: EventType)` → mypy статически (прод-рефактор, архитектор). Зубастая только `producer_envelope`-прогон.
- **M2 major [prod]+[test] (эскалация)** подтверждён баг (а): не-JSON → crash-loop (DoS-привкус, backoff до 60с×попытки), асимметрия с poison-drop schema-invalid. Тест `test_subscriber_malformed_non_json_payload_is_not_acked:213` `pytest.raises(JSONDecodeError)` ЗАМОРОЗИЛ дефект в спеку (A6-нарушение). Фикс: прод → не-JSON poison-drop+ack; тест → под контракт.
- **M3 major [prod] (эскалация)** подтверждён баг (б): `_is_known_event_type` дважды мёртв → метрика `siem_unknown_event_type` недостижима. Удалить мёртвый код/метрику или строковое поле для реального soft-mode.
- **m3 minor [prod?] (эскалация)** 5 emission-сайтов `security_event=True` без `event_type` → `processor.py:40` дропает как `missing_event_type` → молчаливая потеря событий. Зафиксировать гэп/проверить намеренность.
- **m1/m2/m4 minor [test]** shared-object near-тавтология; дедуп-метрика считает дубль и в `ingested`, и в `duplicate` (сверить с дашбордом); severity/tz edge сериализации до колонок БД не докрыты.
- Чисто: vocabulary-стражи (Literal⇔constants⇔__all__), event_writer integration (ON CONFLICT, at-least-once), subscriber ingest (sociable+real PG, transient-формы), `producer_envelope` wire-cross-side, A6.

## S3 — Agent runtime (78 passed) — Ф3-отчёт (Ф4-ревью ожидается)

- **[infra] КРОСС-СКОУП** Харнесс-гэп: `fake_chat_model` (`packages/testing/fakes.py`) → `GenericFakeChatModel.bind_tools` кидает `NotImplementedError`; рекламируемый шов `GraphFactory(model_factory=model_factory(fake))` не драйвит граф (`build_graph` зовёт `model.bind_tools`). S3 обошёл локальным `ToolBindingFakeChatModel`. Ф5: добавить `bind_tools` в харнесс-фейк (релевантно всем, кто драйвит граф через фабрику).
- **[prod/arch] (эскалация)** Второй model-creation point вне шва C1: `_reduce_context` (context compaction) создаёт summarization-клиент в обход инъектируемого `model_factory` → детерминированно не покрывается без правки прода. Решение: расширить шов на summarization или принять как непокрытое.
- Багов прода нет. Покрыто: nodes/edges/ReAct/state-accum/tool-error/guard-ветки/HITL(interrupt+resume)/model-failure; шов `model_factory` (fake + дефолт→прод); stream_events/checkpoint_history/tracing(fail-safe)/runner(sociable SSE).

### S3 — Ф4-ревью (вернулось)
- **M1 major [test]** `_reduce_context` (компактизация, `graph.py:63`) не покрыт. ⚠️ Опровергает эскалацию выше: функция принимает `summarization_model` ПАРАМЕТРОМ → юнит-тестируема напрямую фейком, ШОВ НЕ НУЖЕН. Фикс: 3 юнита (порог не перейдён→passthrough; перейдён→summary+RemoveMessage; ainvoke бросает→trim-only fallback). Эскалацию про summarization-шов СНИМАЕМ.
- **M2 major [test]** ветки `security_block` раннера (mid-stream/final/in-graph, `runner.py:210/252/274`) не покрыты (реальный enforcer с `guard=None` рано возвращает). Фикс: стаб-энфорсер, возвращающий `SecurityOutcome`; ассертить `security_block` + отсутствие последующих чанков.
- **M3 major [test]** позитивный контракт трейсинга не ассертится (только disabled-noop/fail-safe). Эталонный mock-кейс §Дубли пропущен. Фикс: spy-span, `score_trace.assert_called_once_with(payload)` на enabled-успехе.
- **M4 major [test]** `tool_start/tool_end/artifact_created` не прогнаны через реальный `astream` (маппер кормят руками; happy-path раннера без tool-модели). Фикс: integration раннера с echo-tool.
- **m1-m5 minor [test/infra]** fail-safe трейсинг не различает swallow vs never-called; `test_cancel_unknown_thread` тавтология; `bind_tools`-no-op маскирует регрессию (харнесс-гэп → фикс фейка); mid-stream отмена не покрыта; явный SUSPICIOUS на графе.
- Чисто: ReAct/роутинг/аккумуляция через `ainvoke`/`aget_state`, HITL наблюдаемый, дефолт model_factory доказан, `text_chunk` wire корректен (расхождения S5 здесь нет), A6 (seam санкционирован).

## S7 — Memory · settings · MCP · models (98 passed) — Ф3-отчёт (Ф4-ревью ожидается)

- **[prod/security?] (эскалация)** `url_validator` не проверяет схему URL и не следует редиректам — таких веток в коде НЕТ. Для SSRF-валидатора это потенциальный пробел прода (редирект на приватный IP, не-http схема), не баг контракта. Вопрос архитектору: ужесточать ли валидатор.
- Багов прода нет. Покрыто: REST (settings allowlist-422/null-clear, models, user-memory INJECTION→422, mcp ownership-404/scope-409/invalidate); сервисы sociable (каскад резолва модели, McpServerService guard→SSRF→encrypt→persist + 503 + ревалидация по url-но-не-key, MCPToolResolver кэш/деградация/dedup/MAX); url_validator SSRF-глубина (приватные v4/v6, DNS-rebinding fail-closed); репо integration; agent-tools.
- Непокрыто (осознанно): реальный wire MCP-клиента (сеть вне unit), thread-scope MCP-роуты (идентичны покрытым).

### S7 — Ф4-ревью (вернулось)
- **MAJOR [prod-security] (эскалация)** `url_validator.py:44` SSRF-дыры: не нормализует `.ipv4_mapped` → `::ffff:10.0.0.1`/`::ffff:127.0.0.1` проходят; `0.0.0.0` (Linux→localhost) проходит; CGNAT `100.64/10` не блокируется (проверено эмпирически). Фикс: parametrize bypass-формы (покраснеют) + прод: нормализация ipv4_mapped, 0.0.0.0, CGNAT.
- **MAJOR [prod] (эскалация)** `mcp_servers.py:106` `/test`-эндпоинт ловит `except ValueError`, а `validate_url` кидает `InvalidURLError`/`SecurityPolicyViolationError` (← `AppError`, не `ValueError`) → приватный URL даёт 422 вместо `TestConnectionResponse(success=False)`. `/test` не покрыт. Фикс: integration-тест (покажет 422) + прод: ловить правильный тип.
- **MAJOR [test]** MCPToolResolver per-server degradation (`mcp_tool_resolver.py:104`) не тестируется (merge-тесты всегда успешны) — один битый сервер уронит весь merge, пройдёт зелёным. Фикс: merge-тест с одним бросающим `_fetch_tools`.
- **MAJOR [test]+[infra]** REST под-ассерчен: только статус, не problem+json тело (`code`/`reason`); ветка `reason = detection_layer.value` недостижима из-за `StubGuard(detection_layer=None)` (= кросс-скоуп фикс StubGuard). Фикс: ассертить тело 422 + обогащённый StubGuard.
- **m1-m5 minor [test/prod?]** TTL-expiry/negative-caching не покрыты (негатив-кэш отравляет на 5мин — потенц. прод-косяк); `_fetch_tools` целиком фейкается (allowed_tools-фильтр/auth-инъекция непокрыты); кэш-тесты monkeypatch'ат приватный `_resolve_uncached` (impl-coupling); REST-маппинги только user-scope; thread-None cascade.
- **[prod-depth] (эскалация)** TOCTOU/DNS-rebinding: `validate_url` single-shot resolve, реальный коннект (`fetch_remote_metadata`/`_fetch_tools`) резолвит повторно → rebinding+редиректы на приватный IP не перехватываются. Unit-границей не лечится — прод-вопрос.
- Чисто: mcp_server_service образцовый (реальный шифр round-trip, гейтинг ревалидации, 503), model_config_resolver каскад, user_memory store-state, repo-integration, skills path-escape, StubGuard-сигнатура совпадает (S5-M2 здесь нет).

---

## Сводка прод-багов/дефектов (для решения архитектора — фиксить в feat-009 или отложить)

| # | Скоуп | Дефект | Размер | Тип |
|---|-------|--------|--------|-----|
| P1 | S5 | SSE mid-stream error payload `message` vs `detail` → фронт `onError(undefined)`, пустой toast | мал | user-facing |
| P2 | S1 | 500 вместо 401 на валидной подписи с битым/без `sub` (+утечка стектрейса) | мал | auth-critpath |
| P3 | S7 | url_validator SSRF bypass (ipv4-mapped v6, 0.0.0.0, CGNAT) | мал-сред | security |
| P4 | S7 | `/test`-эндпоинт ловит не тот тип исключения → 422 вместо `{success:false}` | мал | контракт |
| P5 | S4 | DELETE проекта не идемпотентен (404 вместо 204, api.md) | мал | контракт |
| P6 | S8 | не-JSON payload → crash-loop (DoS-привкус) vs poison-drop | сред | надёжность |
| P7 | S8 | `_is_known_event_type` мёртв → метрика недостижима | мал | cleanup |
| P8 | S8 | 5 emission-сайтов `security_event=True` без `event_type` → молчаливый дроп | ? | аудит |
| P9 | S9 | `<label>` не связаны с инпутами (a11y) | мал | a11y |
| P10 | S7 | TOCTOU/DNS-rebinding в url_validator (validate→reconnect) | сред | security-depth |

## Решения архитектуры/скоупа (для архитектора)
- **D1 Фронт-скоуп (S9 M4):** `pages/security/*`, `pages/user-settings/*` (мутации, не glue) — ноль тестов. Покрывать в feat-009 или зафиксировать долгом?
- **D2 S8 cross-side (B1):** типизированный `emit_security_event(event_type: EventType)` (mypy-статика, прод-рефактор) vs backend-side контракт-тест. Сейчас cross-side номинален.
- **D3 Repo/trace_store Protocols (S5 M2):** ввести Protocol-интерфейсы для repo/trace_store фейков vs оставить `# type: ignore`.

## Кросс-скоуп фиксы инфры (Ф5, я делаю — packages/testing)
- StubGuard: param `detection_layer` + запись kwargs в `.calls` (S2 MAJOR-1/2, S6 M1, S7).
- fake_chat_model: `bind_tools` (S3 — рекламируемый шов не драйвит граф).
- Redis-testcontainer фикстура (S8 trace_store-блокер).
- `make` цель для `packages/siem-contracts/tests` в гейт (S8-блокер).

## S9 — Frontend (78 passed) — самая слабая зона по критпутям

- **M1 major [test]** Select-взаимодействие не приводится в действие нигде: ModelSelector (write-ветка `handleChange`→PUT settings, маппинг `__default__→null`, disabled-on-pending) и MCPServerForm (переключение transport `http→sse`+сабмит) не покрыты — ядро «селектора» не тронуто. Фикс: тест открывает Select (`user.click`→`findByRole("option")`→клик) + ассерт MSW PUT. Если popup не открывается в jsdom даже с polyfill — эскалация.
- **M2 major [prod]+[test]** РЕАЛЬНЫЙ a11y-дефект: `<label>` без `htmlFor`/`id` (0 совпадений в скоупе), у Sphere textarea вообще нет label. Тесты маскируют через `getByPlaceholderText`. Фикс: тесты → `getByLabelText` (упадут, обнажат), прод → связать подписи (`htmlFor`+`id`/обернуть/`aria-label`). Дрейф-фикс на месте.
- **M3 major [test]** SSE-критпуть ~5/12 веток: не покрыты `cancel()` (+подавление `onError` при отмене), first-byte timeout, 401→refresh→retry, `artifact_created`/`tool_start|end`/`final_output_review_*`, «соединение прервано». Критпуть → глубина обязательна.
- **M4 major [scope] (эскалация)** Целые слайсы без тестов: `pages/security/ui/*` (SecurityRouteGuard — auth-смежная защита маршрута; SecurityRules — create/delete мутации; Filter/Pagination/Events), `pages/user-settings/ui/*` (CustomInstructions/AgentMemory — мутации). Не glue. Вопрос: входят ли в DoD feat-009? Если да — блокер сдачи; если нет — зафиксировать как долг, не оставлять молча зелёным.
- **m1-m4 minor [test/prod]** icon-button без accessible name (SphereView edit, `aria-label`); toggle ассерт на payload, не на видимое состояние; `getAllByText(...).length>0` слабый; `useAgentStream` читает стор динамическим импортом (пограничн., ок).
- Чисто: изоляция (свежий QueryClient+retry:false, MSW reset, zustand reset), MSW — настоящий перехват без самопроверки моков, integration-центр тяжести реален, unit поведенческий, нет querySelector/className/snapshot.
