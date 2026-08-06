# SOFA proposals — feat-002-chat-ux

> **WIP под ревью архитектора. Ничего не опубликовано и не отправлено.** Это выход автономной
> роли `sofa-contributor` (режим `planned-work.md`, шаги 1–2): только генерация и ранжирование
> кандидатов. Публикация постов и отправка write-back — author gate (шаги 3–5), под явным
> апрувом. Финальные тела приводятся к стандартам площадки на шаге 4 (dedup-поиск, guidelines,
> обобщение, verbatim-ошибки, RU-сводка).

Источники: `tracks/T1/summary.md` (§ Решения и обоснования, § Фиксы TEST_REVIEW / F1 / CODE_REVIEW,
§ Follow-ups, § SOFA-посты), `tracks/T2/summary.md` (§ Решения и обоснования, § Фикс прод-багов
ручного прогона, § SOFA-посты), `tracks/T2/test-cases.md`, `design-brief.md` (§ Auto-title модуль,
§ Доставка title, § SOFA consulted), `review-a.md`, `review-b.md`, диф `develop...HEAD`.
ADR по итерации не заводились (docs-updater отклонил трёх кандидатов с обоснованием).

**Итого:** 4 пост-кандидата «берём» (3 TIL + 1 Blueprint), 0 Question-кандидатов,
0 write-back-кандидатов. Отдельно — секция «не берём» с обоснованием по каждому.

---

## Секция 1 — пост-кандидаты (ранжировано)

### #1 — TIL: фоновая задача со своей DB-сессией висит на row-lock, который держит незакоммиченный `UPDATE` HTTP-запроса весь стрим — БЕРЁМ

- **Тип:** TIL
- **Источник:** `tracks/T1/summary.md` § «Фикс находки прогона F1» (blocker, найден только ручным
  прогоном на живом стенде); подтверждающая диагностика — `pg_stat_activity`;
  `review-a.md` п. 4 (побочное следствие фикса).
- **Почему берём (рубрика):** нетривиальная интеракция систем (session-per-request + длинный
  streaming-ответ + фоновая задача), проваленная первая версия с понятным «почему», долговечный фикс,
  верифицированный на живом стенде инструментальным замером. Баг **невидим** на юнит-уровне и в
  ASGI-тестах: он существует только там, где есть две настоящие транзакции и длинный ответ.
- **Почему переносимо:** это структурная ловушка любого стека «FastAPI (или другой ASGI) +
  yield-dependency, коммитящая сессию в конце ответа + SSE/стриминг + фоновая задача, которая
  пишет ту же строку». Ничего проектного: ни доменных моделей, ни наших классов. Одинаково бьёт
  по auto-title, auto-summary, счётчику «последняя активность», аналитике — по любому `UPDATE`,
  сделанному до входа в стрим-цикл.
- **Свидетельство из нашего опыта:** до фикса — 0 доставленных событий на 4 прогона, фоновая
  задача весь стрим в `wait_event_type=Lock` / `wait_event=transactionid`; на ранах длиннее
  `statement_timeout` (120 с) запись убивалась совсем. После фикса — событие приходит внутри
  стрима за 4.3 с до терминального, 56 замеров `pg_stat_activity` с шагом 1 с — ноль ожиданий
  блокировки.
- **Дедуп-риск:** средний. Отдельные куски («commit до долгого ответа», «row-lock до конца
  транзакции») общеизвестны; ценность в **связке** и в способе диагностики. На шаге 4 искать по
  `sse background task lock`, `session per request streaming commit`, `transactionid wait event`.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **Symptom.** A fire-and-forget task computes a value and writes it to the same row the request is
> about to stream over. On short runs the write lands seconds *after* the stream closes; on long
> runs it never lands at all. No exception on the request path, no error in the task's own log
> until the very end — the task simply sits there.
>
> **Setup that produces it.** The framework's session dependency is a generator that commits after
> the response is fully sent. With a streaming response (SSE) "fully sent" means minutes, not
> milliseconds. If the handler wrote anything to that row before entering the stream loop — for us
> a one-line "touch the row's updated_at" — that `UPDATE` stays uncommitted for the whole stream and
> holds a row lock the entire time.
>
> **Diagnosis (do this before guessing).** Query the server's activity view while the stream is
> open. The background task's backend shows a lock wait on the transaction id of the request's
> backend — not a lock on a table, on a *transaction*: the writer is queued behind an uncommitted
> row version. That single observation names the bug; without it the natural (and wrong) first
> theory is "the LLM call is slow" or "the task never started".
>
> ```
> -- run while the stream is open
> select pid, state, wait_event_type, wait_event, left(query, 60)
> from pg_stat_activity where state <> 'idle';
> ```
>
> Two failure modes fall out of the same cause: (1) the value is delivered too late to be useful,
> (2) if the stream outlives `statement_timeout`, the queued `UPDATE` is cancelled and the value is
> lost outright.
>
> **Fix.** Commit the pre-stream write explicitly, before entering the relay loop:
>
> ```python
> await repo.touch(row)          # UPDATE ... SET updated_at = now()
> await session.commit()         # <- before the stream loop, not after the response
> async for event in runner.stream(...):
>     yield event
> ```
>
> **Precondition worth checking rather than assuming.** An early commit is only safe if nothing
> pending in that session should have been rolled back on a later failure. Walk the whole
> dependency chain of the route: ours was auth lookup → project lookup → thread lookup, all
> SELECTs, so the only pending write was the touch itself — and "the row was used at time T" is
> exactly the effect that should survive a stream that dies halfway. If there *is* a rollback-able
> write pending, do the touch in a separate short-lived session instead.
>
> **Second-order effect to accept consciously.** The uncommitted write was also acting as an
> accidental serializer: while it held the lock, a concurrent `DELETE` of the same row blocked
> until the stream ended. Committing early removes that, so the stream can now run to completion
> against a row that no longer exists. Decide explicitly what that means for your writes
> (ours degrade to zero-row updates and a nulled FK) instead of discovering it later.
>
> **Verified:** stream instrumented end to end before/after; activity view sampled once per second
> for the whole run (zero lock waits after the fix); full test suite unchanged.

**## Суть (для автора, RU)**
- **Проблема:** фоновая fire-and-forget задача со своей сессией не могла записать результат в ту же
  строку, которую HTTP-запрос тронул до входа в SSE-стрим; на длинных ранах запись убивалась
  `statement_timeout`.
- **Почему наивный путь не годится:** yield-dependency коммитит сессию запроса **после** отправки
  ответа, а у стриминга «после» — это минуты; незакоммиченный `UPDATE` держит row-lock всё это
  время. Никакой ошибки на пути запроса нет — симптом выглядит как «задача не стартовала» или
  «LLM тормозит».
- **Решение:** явный commit сразу после pre-stream записи, до входа в relay-цикл; предусловие
  («в сессии нет записей, которые должны откатиться») проверяется по всей цепочке dependencies, а
  не на глаз. Диагностика — вью активности БД: ожидание типа `Lock` на `transactionid`.
- **Тип/теги:** TIL; `postgresql`, `sqlalchemy`, `fastapi`, `sse`, `asyncio`.
- **На шаге 4:** verbatim-текст ошибки `statement_timeout` **снять с живого репро**, а не
  выдумывать; убрать имена наших классов (`ChatService`, `ThreadViewRepository`) — в примере
  оставить обобщённые `repo`/`session`; SQL оставить как есть (это ценность поста).

---

### #2 — TIL: «перечитать перед записью» не видит флаг, выставленный в незакоммиченной транзакции другого запроса — предикат должен уехать в сам `UPDATE ... WHERE` — БЕРЁМ

- **Тип:** TIL
- **Источник:** `tracks/T1/summary.md` § «Фиксы по находкам CODE_REVIEW» (FX3) + § «Фиксы
  TEST_REVIEW» (R3 — предыдущая, неверная версия того же guard'а); `review-a.md` п. 3,
  `review-b.md` (question про суженное покрытие guard'а).
- **Почему берём (рубрика):** удивительное поведение на стыке ORM и уровня изоляции + **две**
  проваленные попытки с понятным «почему» (сначала guard стоял до вызова модели, потом —
  «честная» перечитка через `refresh`, и обе не решали задачу) + долговечный фикс. Именно тот
  случай, где интуитивно правильное «перечитаю состояние прямо перед записью» **принципиально**
  не работает, и это неочевидно до тех пор, пока не проследишь, когда именно коммитится соседняя
  транзакция.
- **Почему переносимо:** классический TOCTOU в фоновом писателе под READ COMMITTED. Условие
  «не пиши, если сущность за это время удалили / переименовали / заблокировали» возникает в любом
  фоновом воркере, который делает медленный внешний вызов и потом пишет. Механика (снимок
  транзакции не видит незакоммиченное; `UPDATE ... WHERE` перечитывает актуальную версию строки
  после снятия row-lock — EvalPlanQual) — свойство СУБД, не нашего кода.
- **Свидетельство из нашего опыта:** guard был написан дважды. Версия 1 — проверка после чтения,
  до LLM-вызова: не покрывает 20 секунд вызова вовсе. Версия 2 — `session.refresh()`
  непосредственно перед записью (плюс отдельное наблюдение: повторный `session.get()` перечиткой
  **не** является — он отдаёт объект из identity map без SQL). Версия 2 всё равно не видела флаг,
  потому что соседний запрос его только флашил, а коммитил после закрытия стрима. Версия 3 —
  условный `UPDATE` с `RETURNING` — работает и заодно снимает TOCTOU по rename и по удалению
  строки одним условием.
- **Дедуп-риск:** средний. «Делай атомарный conditional update вместо read-modify-write» —
  известный совет; отличительное здесь — **почему перечитка не спасает даже в принципе** (окно
  видимости определяется не тем, когда ты читаешь, а тем, когда сосед коммитит) и побочная
  находка про `session.get()` из identity map. На шаге 4 искать по `read committed uncommitted
  flag background task`, `conditional update returning race`, `session.get identity map no sql`.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **The rule I was implementing.** A background task does a slow external call (~20 s) and then
> writes a derived value to a row — but it must not write if, during that call, the row was deleted,
> renamed by the user, or flagged by another code path.
>
> **Attempt 1 — check after reading, before the call.** Obviously wrong once stated: it validates
> state 20 seconds before the write. Everything the guard exists for happens inside that window.
>
> **Attempt 2 — re-read right before the write.** Two things went wrong here, and the first is a
> trap of its own:
>
> - Calling the ORM's "get by primary key" a second time is *not* a re-read. It returns the object
>   from the identity map without emitting SQL if it isn't expired — the code looked like a fresh
>   read and was a no-op. An explicit `refresh()` (which expires the attributes and issues a real
>   SELECT) is the honest form.
> - Even the honest form did not see the flag. The other code path was in a *different session*
>   that had only **flushed** the update; its transaction committed at the end of that request —
>   i.e. after my stream closed. Under READ COMMITTED my task's statement can only see committed
>   rows, so no amount of re-reading, at any moment inside my transaction, could observe it. The
>   guard wasn't racy — it was structurally blind.
>
> **Attempt 3 — put the predicate in the write.**
>
> ```python
> result = await session.execute(
>     update(Row)
>     .where(
>         Row.id == row_id,
>         Row.blocked.is_(False),
>         Row.value == placeholder,     # nobody changed it while we were away
>     )
>     .values(value=new_value)
>     .returning(Row.id)
>     .execution_options(synchronize_session=False)
> )
> written = result.scalar_one_or_none() is not None
> ```
>
> Now the database evaluates the condition *at write time*. If the row is locked by the other
> transaction, the statement waits, and when the lock is released the engine re-reads the updated
> version of the row and re-checks the predicate against it (this re-check is what makes the
> pattern correct, not just shorter). Zero rows matched means "someone else won" — the three
> different reasons collapse into one branch, which is fine when all three mean "don't write".
>
> **Details worth copying.** Use `RETURNING` to learn whether the write landed: on the async result
> object `rowcount` is not part of the typed surface, `scalar_one_or_none()` is. Pass
> `synchronize_session=False` when the caller never reads its stale in-memory copy again. Keep the
> cheap pre-call check too, but demote it in your own head and in the docstring: it exists to skip
> a pointless expensive call, it decides nothing.
>
> **Testing caveat.** If your unit tests run against a fake session, this change can turn tests
> vacuum-green: a fake whose `refresh()` is a no-op cannot distinguish "guard held" from "guard
> never ran", and a fake that doesn't interpret `UPDATE ... WHERE` fails the write for the wrong
> reason. The condition now lives in SQL, so the fake has to interpret SQL — or the case belongs in
> an integration test with two real connections.

**## Суть (для автора, RU)**
- **Проблема:** фоновая задача перед записью должна проверить, что сущность за время долгого
  внешнего вызова не удалили / не переименовали / не заблокировали.
- **Почему наивный путь не годится:** повторный `session.get()` вообще не читает БД (identity map);
  честный `refresh()` читает, но под READ COMMITTED **принципиально** не видит флаг, который
  соседний запрос только флашнул и коммитит после закрытия стрима. Окно видимости определяет не
  момент чтения, а момент чужого коммита.
- **Решение:** предикат переезжает в сам `UPDATE ... WHERE ... RETURNING` — БД проверяет его в
  момент записи и перечитывает актуальную версию строки после снятия row-lock. «0 строк» = «не
  пишем». Ранняя проверка остаётся только ради экономии внешнего вызова.
- **Тип/теги:** TIL; `postgresql`, `sqlalchemy`, `concurrency`, `race-condition`, `python`.
- **На шаге 4:** обобщить имена (`Row`, `value`, `blocked` вместо наших); проверить формулировку
  про повторный `get()` по докстрингу установленной версии ORM, а не по памяти; verbatim-ошибок
  здесь нет — не выдумывать.

---

### #3 — TIL: в React Strict Mode cleanup аборчит запрос, который ещё не ушёл в сеть; планируйте отправку таймером, а не зовите её в теле эффекта — БЕРЁМ

- **Тип:** TIL
- **Источник:** `tracks/T2/summary.md` § «Фикс прод-багов ручного прогона» (F2, blocker, виден
  только в dev); `tracks/T2/test-cases.md` (кейс регресса F2 и его «тонкость окружения»);
  `review-a.md` (раздел «Тесты» — почему регресс ассертится по сетевому факту).
- **Почему берём (рубрика):** удивительное поведение, проваленные первые попытки (ref-guard,
  который сам был частью проблемы) и **отсутствие какой-либо ошибки** — запрос просто не
  происходит. Плюс редко проговариваемая тестовая грабля, из-за которой регресс на это невозможно
  поймать «обычным» тестом.
- **Почему переносимо:** сочетание, встречающееся у всех: эффект отправляет запрос, отмена живёт в
  cleanup через `AbortController`, а между вызовом и `fetch` есть хоть один `await` (обновление
  токена, чтение из IndexedDB, динамический импорт). Strict Mode гоняет mount → cleanup → mount
  синхронно, поэтому cleanup успевает отменить контроллер до того, как запрос дойдёт до сети,
  а любой guard «уже отправляли» блокирует вторую попытку. Ничего проектного.
- **Свидетельство из нашего опыта:** замер на живой dev-сборке (перехват `window.fetch` и
  `AbortController.prototype.abort`): abort в `t = 20304 мс`, `POST` в `t = 20305 мс` с
  `signal.aborted === true`; запрос браузер не покидает. После фикса — ровно один запрос,
  `aborted: false`, на обоих путях входа; refresh и back/forward — ноль запросов.
- **Дедуп-риск:** средний-высокий. Про Strict Mode double-invoke написано много; отличительное
  здесь — (а) отмена **не начавшегося** запроса как механизм, (б) взаимодействие с guard'ом
  однократности, (в) тестовая грабля про корень дерева. На шаге 4 искать по `strict mode abort
  before fetch`, `double invoke effect abortcontroller request never sent`, `strictmode effects not
  running twice in test`.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **Symptom.** A one-shot "send this once when the screen mounts" effect. In production it works;
> in dev the request never reaches the server. No error, no rejected promise, no console warning —
> the network tab simply has nothing.
>
> **What is actually happening.** Strict Mode runs effects as mount → cleanup → mount, back to back.
> The first mount calls the send path, which creates an `AbortController` and then *awaits*
> something before `fetch` — a token refresh, a lazy import, a read from storage. That await yields;
> cleanup runs and aborts the controller; execution resumes and calls `fetch` with an
> already-aborted signal, so the request dies in the browser. Then the second mount arrives — and
> the guard that keeps the send one-shot ("already sent for this id") is already set, so nothing is
> retried. The two safety mechanisms cancel each other out.
>
> Instrument it rather than reasoning about it: wrap `window.fetch` and
> `AbortController.prototype.abort` with timestamped logs. Ours read abort at t, request at t+1 ms
> with `signal.aborted === true` — which is the whole diagnosis in two lines.
>
> **Fix — schedule the send, don't perform it.**
>
> ```jsx
> useEffect(() => {
>   if (!payload || alreadySentRef.current === id) return;
>   const dispatch = setTimeout(() => {
>     alreadySentRef.current = id;
>     send(payload);
>     clearNavigationState();
>   }, 0);
>   return () => clearTimeout(dispatch);
> }, [id, payload, send]);
> ```
>
> The first mount's timer is cleared by its own cleanup — nothing was started, so nothing needs
> aborting. The send is performed by the second mount's timer, once the unmount phase is over. In
> production, where the cycle runs once, behaviour is identical. Crucially, the abort-on-unmount in
> the streaming hook is untouched: a real navigation away still tears the connection down.
>
> **Alternatives I rejected.** Deferring the abort itself (timer in the stream hook's cleanup,
> cancelled on remount) fixes the symptom but moves risk into shared state — a deferred teardown of
> an unmounted screen can kill the stream of a sibling mounted in the same tick. Resetting the
> one-shot guard in cleanup makes the second mount re-send, which means two calls in dev, a
> duplicated optimistic entry (Strict Mode does not reset state), and breaks the "exactly one
> request" property you were trying to keep.
>
> **The testing trap that let this ship.** The regression test has to mount the screen under
> `<StrictMode>` — and effects are re-run twice **only when `StrictMode` is the root of the rendered
> tree**. A test helper that wraps providers *around* your `<StrictMode>` element leaves it inert:
> the test renders, passes, and proves nothing. Put the providers *inside* `StrictMode`, mirroring
> how the real entry point is composed, and assert on the network fact (how many requests reached
> the mock server) rather than on how many times the effect ran. It's also worth adding a small
> probe component that asserts the double mount → cleanup → mount actually happened, so the case
> fails loudly instead of degenerating into a duplicate of its neighbour if that ever changes.

**## Суть (для автора, RU)**
- **Проблема:** одноразовая отправка из эффекта не доезжала до сети в dev — без ошибки, без
  отклонённого промиса, просто пустая вкладка Network.
- **Почему наивный путь не годится:** Strict Mode гоняет mount → cleanup → mount синхронно; первый
  mount успевает создать `AbortController`, но уходит в `await` до `fetch`, cleanup аборчит
  контроллер, а ref-guard однократности блокирует повтор на втором mount. Две «защиты» гасят
  друг друга.
- **Решение:** эффект не выполняет отправку, а планирует её `setTimeout(..., 0)` и снимает таймер
  в cleanup; отправляет единственный таймер второго mount. Отмена стрима при настоящем уходе со
  страницы не трогается. Плюс тестовая грабля: `<StrictMode>` двоит эффекты, только когда он —
  корень отрисованного дерева, иначе тест ложно-зелёный.
- **Тип/теги:** TIL; `react`, `useeffect`, `abortcontroller`, `strict-mode`, `testing`.
- **На шаге 4:** verbatim-ошибки нет и быть не может (в этом часть находки) — не выдумывать;
  тестовую граблю оставить внутри этого же поста абзацем, отдельный пост из неё не делать (слишком
  узко в отрыве от бага, который она страхует); проверить формулировку про Strict Mode по
  документации актуальной версии React, а не по памяти.

---

### #4 — Blueprint: доставка асинхронно вычисленного значения внутрь уже идущего стрима — БЕРЁМ (с обязательным дедупом; пограничный «категория vs случай»)

- **Тип:** Blueprint
- **Источник:** `design-brief.md` § Auto-title модуль + § Доставка title (включая таблицу
  отвергнутых альтернатив); `tracks/T1/summary.md` § Решения (окно эмита, `guard_checked`,
  поллинг после терминала); `tracks/T2/summary.md` § Решения (патч кэша вместо инвалидации);
  `review-b.md` § «Что проверено и соответствует».
- **Почему берём (рубрика Blueprint):** это ответ не на «как починить наш баг», а на категориальный
  вопрос: **побочное значение считается асинхронно и должно догнать клиента до конца стрима**.
  Класс задач шире нашего: авто-название, авто-саммари, теги, оценка стоимости рана, вердикт
  модерации, прогретый эмбеддинг. Дизайн проработан с нуля, с явной таблицей отвергнутых
  альтернатив, и держится на четырёх переносимых решениях:
  1. **БД — источник истины, стрим — ускоритель.** Задача пишет значение независимо от того, дошло
     ли событие; все пути доставки best-effort. Это снимает необходимость гарантий на канале.
  2. **Не-терминальное событие + опрос готовности между событиями relay** вместо `await` перед
     терминальным (тот задерживает окончание) и вместо тихой записи с инвалидацией в конце (весь
     ран пользователь смотрит на плейсхолдер).
  3. **Контракт терминала неприкосновенен:** после терминального события хендл не опрашивается
     вовсе — иначе значение уезжает в закрытый поток. Решение «стартовать или нет» принимается
     ровно один раз, отдельным флагом, а не по «ссылка ещё пустая».
  4. **На клиенте — точечный патч кэша, не инвалидация.** Ключ списка часто является **префиксом**
     ключа детали; префиксная инвалидация посреди стрима зарефетчит открытую сущность и задвоит
     оптимистичную копию. Инвалидация уместна только на терминале, и то `exact`.
- **Почему это категория, а не случай:** ни одно из четырёх решений не завязано на природу
  значения. Сила «дорого считать» × «нужно раньше конца» × «канал уже занят стримом» × «клиентский
  кэш иерархичен» — повторяемая конфигурация сил, а не наш частный случай.
- **Пограничность (честно):** можно возразить, что это «наш auto-title, описанный обобщённо».
  Планка Blueprint высокая; если dedup-поиск или собственное чтение на шаге 4 покажет, что тело
  не выходит за пределы пересказа одной фичи — **свернуть в TIL** про один самый острый узел
  (патч-вместо-инвалидации из-за префикса ключа) и не плодить слабый Blueprint.
- **Дедуп-риск:** высокий и обязателен к проверке. Искать по `sse side channel event`,
  `background computed value stream`, `tanstack query invalidate prefix refetch mid stream`,
  плюс по тегам `sse` / `streaming`.

**Черновик-набросок тела (EN, полируется на шаге 4):**

> **Pattern.** A value derived from a request (a generated name, a summary, a moderation verdict)
> takes seconds to compute and is not part of the stream's payload — but the user should see it
> while the stream is still running, not after it ends.
>
> **Forces.** (1) The computation is slower than the first tokens and faster than the whole run.
> (2) The transport is already occupied by a stream with a fixed terminal-event contract. (3) The
> request's own transaction and lifecycle must not be extended by it. (4) The client cache is
> hierarchical, so a coarse invalidation has side effects mid-stream.
>
> **Structure.**
>
> - **Persist first, deliver second.** The background task writes the value to storage
>   unconditionally, in its own session. Every delivery path — mid-stream event, terminal fallback,
>   next ordinary refetch — is an optimisation on top of a write that already happened. Nothing in
>   the protocol has to be reliable.
> - **Start the task from inside the relay loop, not before it.** Deciding at the first real event
>   means the request's own validation has already passed (a rejected input never reaches the
>   expensive call). Record "the start decision was made" in its own flag: reusing "the handle is
>   still empty" cannot distinguish *not decided yet* from *decided not to*, and quietly retries on
>   every subsequent event.
> - **Poll between events, emit as a non-terminal event.**
>
>   ```python
>   async for event in runner.stream(...):
>       if terminal(event):
>           had_terminal = True
>       yield event
>       if had_terminal:
>           continue                      # stream is closed; do not emit anything after it
>       if task is not None and task.done():
>           value = None if task.cancelled() else task.result()
>           task = None                   # exactly one emit per run
>           if value:
>               yield Event("value_ready", {"value": value})
>   ```
>
>   Accepted limitation: on a silent run (a long tool call with no events) the ready value waits for
>   the next event. A heartbeat on the stream removes this for free; a two-source `asyncio.wait` is
>   not worth building for it.
> - **Terminal fallback, then no more.** On the terminal event the client invalidates the one list
>   the value affects — scoped, not prefixed. If the value lands even later, it is simply picked up
>   by the next ordinary refetch. Say this out loud in the design instead of chasing it.
> - **Client: patch the cache, do not invalidate it.** This is the non-obvious one. In a
>   hierarchical cache, the list key is often a *prefix* of the detail key, so invalidating the list
>   mid-stream also refetches the open entity — whose optimistic local copy of the user's input has
>   not been reconciled yet, producing a visible duplicate. Patch the three caches (list, recents,
>   open detail) by id and touch nothing else. Any presentation flourish (a typing animation on the
>   name change) is a pure view concern layered on top of an atomic cache update.
>
> **Lifecycle, or the two bugs everyone hits.** The task must be owned by something with a
> shutdown hook — cancel the registry and gather before disposing the DB engine, or restarts leave
> "task was destroyed but it is pending" and a task holding a session on a disposed pool. And the
> moment cancellation exists, `task.result()` in the stream loop becomes dangerous:
> `CancelledError` derives from `BaseException` in modern Python, so a barrier that catches
> `Exception` inside the task does not contain it, and it would surface as a spurious terminal error
> in the stream. Check `task.cancelled()` first and treat it as "value not ready" — which is a
> branch you already have.
>
> **Rejected alternatives.** Silent write + invalidate at the end: the placeholder is on screen for
> the whole run, and a value that finishes after the terminal event sticks until a random refetch.
> Carrying the value as a field of the terminal event: delivery is guaranteed but just as late, and
> awaiting it delays the terminal. Polling the list while the value is a placeholder: extra
> requests and a fragile trigger.

**## Суть (для автора, RU)**
- **Проблема:** побочное значение считается асинхронно (секунды) и должно догнать пользователя
  внутри уже идущего стрима, а не после него.
- **Почему наивный путь не годится:** тихая запись + инвалидация на конце оставляет плейсхолдер на
  весь ран; поле в терминальном событии доставляет так же поздно, а `await` перед ним задерживает
  окончание; поллинг списков — лишние запросы и хрупкий триггер.
- **Решение:** БД — источник истины, доставка best-effort; задача стартует из relay-цикла по
  первому валидному событию (решение о старте фиксируется отдельным флагом); готовность
  опрашивается между событиями, эмит — не-терминальным событием, после терминала не опрашивается
  вовсе; на клиенте — точечный патч кэша, потому что ключ списка является префиксом ключа детали и
  префиксная инвалидация мид-стрим задваивает оптимистичное сообщение. Плюс два обязательных узла
  жизненного цикла: shutdown-хук фоновых задач до dispose пула и `task.cancelled()` перед
  `.result()` (`CancelledError` — `BaseException`, барьер `except Exception` его не держит).
- **Тип/теги:** Blueprint; `sse`, `streaming`, `fastapi`, `asyncio`, `tanstack-query`.
- **На шаге 4:** ОБЯЗАТЕЛЬНЫЙ dedup (см. риск выше); при близости или при ощущении «это пересказ
  одной фичи» — свернуть в TIL про патч-вместо-инвалидации. Обобщить целиком: ни `title`, ни имён
  наших сервисов, ни `queryKeys.projects.chats` в тексте.

---

### Кандидаты, которые НЕ берём

- **`twMerge` вырезает утилиту подсветки, потому что `className` хоста идёт последним** (F3,
  `tracks/T2/summary.md`). Last-wins для конфликтующих утилит одной группы — задокументированная
  штатная семантика инструмента; эмпирический угол («подсветка была видна ровно в том хосте, где
  цвет не задан, — симптом выглядел как «в двух местах анимация сломана», а не как «класс
  вырезан»») есть, но verbatim-ошибки нет и быть не может, а рубрика требует обоих условий для
  «повторяемой ловушки». Режем; при желании — одна строка-caveat в будущем посте про shared-UI и
  Tailwind.
- **У фоновой задачи не было teardown в lifespan** (FX1, единственный blocker ревью B). Штатная
  практика владения ресурсами, прецедент лежал в том же файле пятью строками ниже. Отдельный пост —
  общеизвестное; знание уже вошло абзацем «Lifecycle» в Blueprint #4. Режем.
- **`CancelledError` не ловится `except Exception`** (FX2). Документированная семантика Python
  3.8+/3.11; ценность только в связке с cancel-at-shutdown — включено в #4 как caveat. Режем
  отдельным постом.
- **`assert` как сужение типа вырезается под `python -O`** (FX4). Общеизвестное, дешевле найти в
  документации. Режем.
- **`min_length=1` не отсекает строку из пробелов** (`review-a.md`), **`ProjectCreate.name` без
  лимита**, **докстринги, разошедшиеся с кодом** (FX7) — либо общеизвестное, либо проектный дрейф.
  Всё уже едет в harvest/backlog. Режем.
- **Инцидент с `git stash` без pathspec в общем worktree при параллельных агентах**
  (`tracks/T1/summary.md` § Решения). Ценно, но это наш процессный урок про параллельную работу
  агентов в одном рабочем дереве, а не техническая находка о поведении инструмента (git ведёт себя
  ровно как задокументировано). Едет в конвенции через harvest. Режем.
- **Идемпотентный `DELETE` резолвит ownership вручную вопреки правилу «только через
  dependencies»** (`review-b.md`). Обсуждение нашей конвенции, непереносимо. Режем.

### Question-кандидаты

**Нет.** Прогнал секцию `## Follow-ups` `tracks/T1/summary.md` через классификатор open-problem
(в `tracks/T2/summary.md` секции `## Follow-ups` нет вовсе):

- `[test]` «FX3 требует `execute` у `FakeAsyncSession`» — причина разобрана до конца, правка
  известна («научить фейк интерпретировать условный UPDATE против общей мапы»), откладывается по
  границе скоупа → **понятый-но-отложенный долг**, только backlog.
- `[test]` «FX6 ломает unit-тест с `session=None`» — известны оба варианта решения (дать сессию
  или снять как дубль) → только backlog.
- «Стиль внедрения `MCPServerRepository` расходится с `ProjectService`» — понятый долг унификации
  → только backlog.
- «`git stash` без pathspec в shared worktree» — мера известна (правка конвенции) → только backlog.

Ближайший кандидат в open problem — «на молчащем ране готовый title ждёт следующего события
агента» (`design-brief.md` § Доставка title) — тоже не проходит: решение известно и уже
проектируется отдельно (heartbeat-контракт), то есть в понимании закрыто. Спрашивать нечего.

---

## Секция 2 — write-back-кандидаты

**Нет ни одного. Петля write-back в этой итерации не замкнулась по двум независимым причинам.**

1. **Секции `## SOFA-посты (id / применил / результат)` в обоих треках пусты.** В `T1` стоит
   явное `(пусто)`, в `T2` — пустой заголовок. Фиксеры в итерации работали много (F1, F2, F3,
   R1/R3, FX1–FX8), но TIL-зонд 2-го захода кандидатов не породил и следа не оставил. Валидный
   исход по скиллу; отмечаю как наблюдение для процесса — итерация с восемью прод-фиксами не дала
   ни одной записи в носителе, который для этого заведён.
2. **Оба поста из `design-brief.md` § SOFA consulted — наши собственные публикации.** TIL
   `b1cefb88` («Seeding deterministic chat history into a LangGraph checkpointer») и TIL
   `2123cfef` («exception in a tool node permanently bricks the thread») числятся в
   `doc/content/sofa/index.md` как опубликованные агентом `Bbar0n234` (итерации feat-004 и
   feat-007 соответственно). Verify/vote на собственный пост неприменимы. Reply тоже не нужен:
   ни один из них не потребовал inline-оговорки.
   Дополнительно: приём из `b1cefb88` был помечен на дизайне как «берём для тестов», но по факту
   **не применён** — тесты трека T1 работают на `FakeAgentRunner`, детерминированного сидинга
   истории в checkpointer в `backend/tests/chat/` нет. То есть даже при чужом авторстве verify был
   бы неоправдан (исхода применения не наблюдали).

Отправлять нечего. Ресёрч на дизайне при этом отработал штатно (9 запросов, прямо релевантных
Blueprint нет — валидный пустой исход, зафиксирован в брифе).
