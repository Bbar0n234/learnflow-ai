# Ф3 · S1 — Auth & access · run-log

Скоуп S1 (критпуть, максимальная глубина). Тесты пишет независимый автор; прод-код
не правился. Все файлы — только в `backend/tests/auth/`.

## Возобновление

Прогон возобновлён после перезагрузки. В тест-директории уже лежали почти готовые
файлы предыдущего прогона. Осмотрел, сверил с прод-кодом построчно (auth-роуты,
сервис, security, deps, репозитории, encryption, rate_limit) — каркас годный, не
переписывал. Достроил: точечно починил один красный тест (см. ниже), привёл
`_helpers.py` к формату ruff, убрал mypy-ошибку в rate-limit-фикстуре.

## Файлы

- `conftest.py` — локальные фикстуры `settings`, `auth_app`, `auth_client`.
  Ключевое отличие от общего харнесса: provider текущего пользователя **не**
  переопределяется → токены минтятся и валидируются по-настоящему
  (`/auth/login` → токен → хождение). Lifespan под ASGITransport не стартует, поэтому
  `app.state.settings`/`rate_limiter` проставляются явно.
- `_helpers.py` — тонкие хелперы для реального HTTP-флоу (`register`/`login`/
  `do_refresh`/`refresh_value`). `do_refresh` чистит jar и шлёт ровно один
  `refresh_token` — нужно для replay-тестов (httpx иначе подмешивает ротированную
  cookie).
- `test_login.py` — register + login через реальный флоу route→service→repo→PG.
- `test_current_user.py` — валидация access-токена на `get_current_user` через
  защищённый `/auth/me`.
- `test_refresh.py` — ротация, replay-детект, отказы.
- `test_logout.py` — отзыв предъявленного токена + очистка cookie.
- `test_rate_limit.py` — солитарный unit на скользящее окно + одна HTTP-проводка.
- `test_encryption.py` — `EncryptionService` solitary-unit.
- `test_refresh_token_repo.py`, `test_user_repo.py` — repository-integration против
  живого PG с транзакционным откатом.

## Покрытые поведения / критпути

- **Логин**: успех (register→login, токен реально ходит в `/auth/me`); неверный
  пароль → 401; неизвестный юзер → 401; дубль имени → 409; короткий пароль → 422.
- **Access-токен** (`get_current_user`): без токена → 401; не-Bearer заголовок →
  401; истёкший → 401; чужая подпись → 401; валидный токен на несуществующего
  юзера → 401 "User not found".
- **Refresh-ротация**: ротация выдаёт новый токен (не reissue), цепочка
  продолжается; повторный старый refresh → replay-детект 401 + revoke-all +
  удаление cookie, после чего и ротированный токен мёртв; без cookie → 401;
  неизвестный → 401; протухший stored-токен → 401.
- **Logout**: HTTP-контракт (200, cookie max-age=0, идемпотентность без cookie);
  отзыв предъявленного токена и no-op на неизвестный — на сервисном слое.
- **Rate-limit** (solitary, инъекция `time.monotonic`): N запросов проходят, N+1
  блок; истечение окна сбрасывает бюджет; ключи независимы; `Retry-After`
  считается до старейшей метки; HTTP: 6-й логин → 429 + `Retry-After`.
- **Encryption**: round-trip (включая пустую строку, юникод, 4 КБ); порча
  ciphertext → `EncryptionError`; чужой ключ → `EncryptionError`; без ключа —
  `is_available=False`, `encrypt`/`decrypt` → `RuntimeError`.
- **Repo (живой PG)**: user — get_by_name/id, none-пути, unique-constraint; refresh
  — create/get_by_hash, revoke, revoke_all_for_user (scoped к юзеру),
  delete_expired_for_user (только протухшие этого юзера).

## Результат

`make test-scope P=backend/tests/auth` → **45 passed**. ruff (lint+format) и mypy по
папке — чисто.

## e2e logout → refresh → 401 (Ф5: диагностика исправлена)

`test_logout` e2e (logout → повторный refresh старым токеном → 401) **писуем и
зелёный** — в Ф3 он падал (200 вместо 401) по причине, ошибочно списанной на
границу харнесса. Эмпирический разбор в Ф5 (одноразовый probe, удалён):

- Прямой вызов `AuthService.logout(raw)` на shared `db_session` → `revoked_at`
  проставляется.
- HTTP `/auth/logout` **без явной cookie** → revoke не выполняется вовсе:
  refresh-cookie scoped на `path=/api/auth`, и httpx **не доставляет** её на
  `/api/auth/logout` автоматически (та же причина, по которой `do_refresh` шлёт
  токен явным `cookies=`). Хендлер видит `refresh_token=None` → no-op.
- HTTP `/auth/logout` **с явной cookie** → `revoked_at` персистится (виден свежим
  SELECT по той же сессии), а последующий `/auth/refresh` старым токеном → 401
  «replay detected».

Итог: причина была не в потере голого `UPDATE` на teardown, а в недоставке
cookie в тесте. In-session revoke **виден** последующему запросу под shared-session
харнессом — ровно как ротация в `test_refresh.py`. Фикс: e2e шлёт cookie явно.
Сервис-слойный тест (`AuthService.logout` → `revoked_at`) оставлен как прямая
проверка персиста. Прод-код не тронут.

## Баги для Ф5

Продуктовых багов не найдено. Поведение совпало с ожиданиями по всем путям.

## Снятое наблюдение (диагностика была ложной)

В Ф3 здесь предполагался харнесс-острый-угол: будто handler, чей единственный
DB-эффект — голый `UPDATE`/`DELETE` без `flush()`, **не виден** последующему
HTTP-запросу под shared-session + rollback-изоляцией. Ф5 эмпирически опроверг:
in-session `UPDATE` logout'а **виден** следующему запросу (см. e2e выше) — голый
`session.execute(update(...))` исполняется сразу против соединения транзакции,
никакого flush для видимости не требуется. Прежняя «потеря на teardown» была
артефактом недоставленной cookie, а не свойством харнесса. Кандидат-заметка в
`testing.md` про «грань bare-UPDATE» — **снята**.

## Непокрытое и почему

- **Конкурентные сценарии в одном тесте** (параллельный refresh, гонка ротации) —
  не покрываю: ограничение харнесса (одна транзакционная сессия, § F2 infra.md).
- **Качество argon2/Fernet-крипто** — вне unit (это свойства библиотек); проверяю
  только наш контракт вокруг них.
- **Реальный rate-limit под нагрузкой/Redis** — нерелевантно: лимитер in-memory на
  `time.monotonic`, инъекция часов даёт полный детерминизм без сна и Redis.

## Блокеры

Нет.
