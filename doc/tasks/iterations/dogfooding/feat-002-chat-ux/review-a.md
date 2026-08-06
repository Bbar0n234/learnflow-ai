# Code Review Report — режим A (качество кода)

Диф: `git diff develop...HEAD` (4 коммита поверх `develop`), вычитан целиком, кроме
`doc/**` и мокапа. Проверялись корректность и поведение (в первую очередь
concurrency), локальный дизайн, читаемость, поведенческая безопасность, тесты.
Проектные конвенции и детерминированно ловимое — не мой скоуп.

Общая оценка: качество высокое. Concurrency-часть (fire-and-forget задача с
реестром, окно эмита между событиями relay, отдельная сессия задачи, отложенная
отправка в React-эффекте) продумана и покрыта тестами, которые действительно
падают при поломке — включая интеграционный row-lock-тест на двух реальных
соединениях и тест «генерация финишировала ровно перед терминальным событием».
Комментарии объясняют «почему», а не «что», и не расходятся с кодом (единственное
исключение — п. 8). Замечания ниже — про узкие гонки на границах и про
несколько мест, где инвариант декларирован, но не защищён.

### Summary

- blocker: 0
- nit: 8
- pre-existing: 0

### Замечания

| Severity | Намерение | Файл:строка | Замечание (со свидетельством поведения) | Предложение |
|---|---|---|---|---|
| nit | issue | `backend/app/main.py:622-638`, `backend/app/services/chat_title.py:700-705` | **In-flight title-задачи не сливаются и не отменяются при shutdown.** После `yield` (main.py:622) lifespan явно гасит `security_publisher_task` (`cancel()` + `await` под `suppress`, main.py:629-632), но `app.state.chat_title_generator._tasks` не трогает вовсе, а на main.py:638 делает `await engine.dispose()`. Задача `_run` (chat_title.py:709) в этот момент может держать сессию из `session_factory` и висеть в `ainvoke` до `LLM_TITLE_TIMEOUT_SECONDS` (20 с). Итог: в лучшем случае `logger.warning("chat title generation failed")` от барьера chat_title.py:741, в худшем — «Task was destroyed but it is pending» и потерянный title. Паттерн отмены фоновых задач в этом же lifespan уже есть — эта задача из него выпала. | Дать `ChatTitleGenerator` метод `shutdown()` (cancel всех задач реестра + `asyncio.gather(..., return_exceptions=True)`) и вызвать его в lifespan до `engine.dispose()` — вместе с п. 2. |
| nit | question | `backend/app/services/chat.py:266-270` | **`title_task.result()` вызывается без защиты от `CancelledError`.** `_run` (chat_title.py:707-750) заворачивает тело в `except Exception`, который `CancelledError` не ловит (в 3.11+ это `BaseException`). Сейчас задачу никто не отменяет, так что это латентно — но станет живым ровно в тот момент, когда п. 1 починят через `task.cancel()`: `.result()` поднимет `CancelledError` внутри SSE-генератора и порвёт поток (`_event_generator` в routes/messages.py:37-44 переведёт это в терминальный `error`). Обоснование в summary («ничто в этом ране задачу не отменяет») верно на сегодня, но перестанет быть верным с фиксом п. 1. Правильно ли я понимаю, что связка задумана именно так? | Либо `if title_task.done() and not title_task.cancelled():`, либо `try/except asyncio.CancelledError` вокруг `.result()` — вводить одновременно с п. 1. |
| nit | question | `backend/app/services/chat_title.py:732-740` + `backend/app/agent/runtime_security.py:290-297` | **Решающий pre-write guard обходится незакоммиченным конкурентным `mark_security_blocked`.** `session.refresh(thread_view)` (chat_title.py:733) читает в собственной транзакции задачи; под READ COMMITTED он не видит `UPDATE thread_views SET security_blocked=true`, который `_mark_blocked` только **флашит** в сессию запроса (runtime_security.py:291-292) и коммитит лишь в конце запроса (`get_db_session`, api/deps.py:48-57). Поэтому `_title_write_blocked` пропускает запись, следующий `repo.update` → `flush` встаёт на row-lock той же строки, а после коммита запроса — записывает title. Результат: `security_blocked` чат получает auto-title, хотя design-brief и docstring `_title_write_blocked` (chat_title.py:642-649) это запрещают. Окно узкое (блок должен прилететь внутри LLM-вызова), эффект косметический — но именно тот случай, ради которого guard и вводился фиксом R3. | Заменить пару «refresh + проверка + update» на условный `UPDATE ... WHERE thread_id=:id AND security_blocked = false AND title = :placeholder` (одна атомарная операция, заодно снимает и TOCTOU по rename), либо `refresh(..., with_for_update=True)`. |
| nit | question | `backend/app/services/chat.py:196-211` (фикс F1) | **Ранний commit снял row-lock, и вместе с ним — неявную сериализацию «нельзя удалить чат, пока он стримит».** До фикса незакоммиченный `touch` держал строку, поэтому `DELETE /chats/{id}` ждал конца стрима. Теперь `delete_chat` (chat.py:91-120) коммитит удаление сразу, а `send_message` после входа в relay-цикл существование треда больше не перепроверяет: поток честно доиграет до `done` для чата, которого уже нет. Побочные записи в этом окне деградируют тихо (`mark_security_blocked` — UPDATE по нулю строк; `artifacts.thread_id` — `ondelete="SET NULL"`, models/artifact.py:30-32), но вставка нового артефакта тем же раном упрётся в FK на удалённый `thread_views`. Гонка узкая и до фикса была недостижима — стоит зафиксировать как осознанно принятую, а не найденную ревью. | Осознанно принять и записать в summary/бриф; при желании — проверять `EntityNotFoundError` в post-hoc блоке (chat.py:277-293) и закрывать поток `error` вместо `done`. |
| nit | issue | `backend/app/api/schemas/chats.py:9` | **`ChatUpdate.title` пропускает название из одних пробелов.** `Field(min_length=1, max_length=MAX_TITLE_LENGTH)` считает длину до strip, поэтому `PUT {"title": "   "}` проходит валидацию, а `rename_chat` (chat.py:70-76) пишет строку как есть — в списке чатов появляется пустая строка. Фронт от этого защищён своим `trim()` (ChatActions.tsx:61), т.е. бьёт только по не-браузерным клиентам, но валидация схемы — то место, где это должно отсекаться. | `title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)` + `StringConstraints(strip_whitespace=True)` (или `field_validator`, приводящий к `.strip()` до проверки длины). |
| nit | question | `backend/app/services/constants.py:16-19`, `backend/app/services/chat.py:225-228`, `backend/app/services/chat_title.py:649` | **Инвариант «плейсхолдер не совпадает с пользовательским названием» задекларирован, но ничем не защищён.** Докстринг `DEFAULT_CHAT_TITLE` прямо говорит «must never collide with a user- or LLM-chosen title», а триггер — обычное сравнение строк (`thread_view.title == DEFAULT_CHAT_TITLE`). Пользователь может переименовать чат ровно в «Новый чат» через `PUT` — и следующее сообщение молча перезапишет его название сгенерированным. Влияние низкое, но докстринг обещает больше, чем делает код. | Либо ослабить формулировку докстринга до фактической («триггер — точное совпадение с этой строкой; переименование в неё снова включает генерацию»), либо отсекать плейсхолдер на входе `ChatUpdate` — но это уже продуктовое решение архитектора. |
| nit | suggestion | `backend/app/services/chat.py:250` | **`assert self._title_generator is not None` в проде — только ради сужения типа.** `should_generate_title` (chat.py:225-228) уже гарантирует не-None, а `assert` вырезается под `python -O`, после чего строка ниже упадёт в `AttributeError` внутри генератора. Читателю также приходится доказывать себе связь между флагом и assert'ом. | Поднять локальную переменную до цикла: `generator = self._title_generator` и `should_generate_title = generator is not None and ...`; mypy сузит `generator` по флагу без assert'а. |
| nit | suggestion | `backend/app/services/chat.py:91-110` | **Докстринг `delete_chat` объявляет cleanup обязательным, а код делает его условным.** «the DB-side transaction (polymorphic disables cleanup + row delete + commit) runs first and is the source of truth» (chat.py:94-96) — при этом и cleanup (строки 104-107), и `commit` (109-110) стоят под `if self._session is not None`, т.е. при `session=None` строка удаляется без подчистки disables и без коммита, но лог `"chat deleted"` и `agent_runner.delete_thread` отрабатывают как при успехе. В проде `session` всегда задан (`api/deps.py:118-125`), так что это форма ради тестовых конструкторов — но два утверждения расходятся. | Либо оговорить в докстринге, что при отсутствии сессии (тестовая форма) cleanup/commit пропускаются, либо сделать `session` обязательным для этого метода. |

### Тесты (раздел E)

Замечаний нет. Проверял на «упадёт ли тест, когда код реально сломается»:

- `test_auto_title_row_lock.py` — единственный уровень, на котором F1 наблюдаем
  (две реальные транзакции, `lock_timeout` превращает зависание в именованный
  `pytest.fail`); на уровне фейков и ASGI этот баг невидим, и это в тесте
  объяснено, а не обойдено.
- `test_auto_title_relay.py` — окно эмита пинается через `FakeAgentRunner.on_event`
  + `FakeTitleGenerator(mode="deferred")`: параметризация
  `next_event_is_not_terminal / is_error / is_block` при одинаковом тайминге
  отличается ровно типом события, т.е. проверяется именно контракт «после
  терминального ничего не идёт», а не совпадение.
- `FakeAsyncSession` (conftest.py) моделирует изоляцию снапшот↔store так, что
  «перечитка перед записью» отличима от первого чтения — без этого тесты
  guard'ов R3 были бы вакуумными; в conftest это прямо и написано.
- `ChatThread.test.tsx` — регрессия F2 ассертится по сетевому факту (сколько
  POST дошло до MSW), а не по числу проходов эффекта, плюс `EffectPassProbe`
  страхует кейс от вырождения, если двойной проход перестанет случаться.
- `TypedTitle.test.tsx` — регрессия F3 проверяется на классах (в jsdom с
  `css: false` computed-цвет ничего бы не показал) и дополнена двумя
  cleanup-кейсами с `vi.getTimerCount()`.

Ложных срабатываний и ассертов «на реализацию вместо поведения» не нашёл.
