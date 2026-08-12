# SOFA-кандидаты — feat-008 (OAuth + экраны входа)

**Статус: WIP под ревью архитектора. Ничего не опубликовано и не отправлено.** Роль
`sofa-contributor` в конвейере только генерирует кандидатов; публикация постов и отправка
write-back (verify/vote/reply) — author-driven действие под явным апрувом (SKILL § Author gate).

Источники: `tracks/T1/summary.md` (§ Решения и обоснования, § Verification, § Follow-ups),
`tracks/T2/summary.md`, `tracks/T1/test-cases.md` (§ Проверка мутацией, § Инцидент харнесса),
`design-brief.md` (§ SOFA consulted, § Ревью брифа), `review-a.md`, `review-b.md`,
`ADR-031-oauth-identity-model.md`, diff итерации.

Итого: **6 пост-кандидатов «берём»** (5 TIL + 1 Blueprint), 14 отсеяно, **1 write-back-кандидат**
(reply, низкий приоритет).

---

## Пост-кандидаты (ранжированы)

### 1. TIL — structlog + rich печатает locals в трейсбеках, и туда попадает объект настроек с секретами

**Тип:** TIL. **Решение: берём** — первое место по ценности: сюрприз в дефолте популярной
библиотеки, внешне достижимый триггер, следствие — утечка секретов открытым текстом, фикс в одну
строку. Переносимо на любое приложение со `structlog` + установленным `rich` в human-readable
режиме логов, независимо от фреймворка и домена.

**Источник:** `tracks/T1/summary.md` § Решения и обоснования (последний пункт — «Locals выключены у
rich-рендера трейсбеков»); фикс — `backend/app/infra/logging.py:41-49`.

**Верифицировано:** дефолт снят с установленного пакета прямо сейчас (не по памяти):

```
structlog 25.5.0
ConsoleRenderer.__init__(..., exception_formatter: ExceptionRenderer =
  RichTracebackFormatter(color_system='truecolor', show_locals=True, max_frames=100, ...))
```

плюс наблюдение утечки в логе процесса на фазе T1.8 («временные логи с выводом `Settings()`,
содержавшим креды в открытом виде»).

**Набросок тела (EN, финал приводится к стандартам площадки на шаге 4):**

> `structlog.dev.ConsoleRenderer` — the default renderer in human-readable mode — formats
> exceptions with `RichTracebackFormatter`, and that formatter defaults to `show_locals=True`
> whenever `rich` is importable. Every frame in the traceback then prints its local variables. If
> any frame on the failing path holds a settings/config object, its `repr` lands in stdout and in
> the log file: API keys, JWT signing secret, OAuth client secrets.
>
> Repro (no app needed): print `inspect.signature(structlog.dev.ConsoleRenderer.__init__)` — the
> default `exception_formatter` renders as
> `RichTracebackFormatter(color_system='truecolor', show_locals=True, max_frames=100, ...)`
> (structlog 25.5.0). Then log any exception raised from a frame that has a config object in scope.
>
> Why it is easy to miss: the leak needs no logging of secrets anywhere in your code. It is enough
> that one `logger.warning(..., exc_info=True)` fires on a code path where a settings object is a
> local or an attribute of a local. In our case an unauthenticated request with a garbage query
> parameter was enough to trigger the branch.
>
> Fix — pass one shared formatter with locals off to every human-readable renderer you build:
>
> ```python
> formatter = structlog.dev.RichTracebackFormatter(show_locals=False)
> console = structlog.dev.ConsoleRenderer(exception_formatter=formatter)
> to_file  = structlog.dev.ConsoleRenderer(colors=False, exception_formatter=formatter)
> ```
>
> Stack, line numbers and source context survive; only the locals panel disappears. JSON renderers
> never render locals and are unaffected. Wrapping secrets in a secret-string type is the deeper
> defence, but it touches every read site — turning locals off is the one-line stopgap that closes
> every emit site at once.

**Суть (для автора, RU):** `ConsoleRenderer` из `structlog` в человекочитаемом режиме отдаёт
трейсбеки в rich, а rich по умолчанию печатает locals каждого фрейма — то есть любой
`exc_info=True` на пути, где в области видимости лежит объект настроек, выливает все секреты в
stdout и в файл лога. Наивный путь «мы же нигде не логируем секреты» не спасает: логирует не наш
код, а рендерер. Решение — один общий `RichTracebackFormatter(show_locals=False)`, переданный обоим
человекочитаемым рендерам; стек и контекст кода остаются, панель locals исчезает. Тип TIL, теги
вокруг structlog / rich / logging / secrets.

---

### 2. TIL — на psycopg3 имя нарушенного constraint лежит в `exc.orig.diag.constraint_name`, а не плоским атрибутом

**Тип:** TIL. **Решение: берём** — классическая тихая ошибка: код, скопированный из asyncpg-примеров,
не падает, а молча возвращает `None`, и вся ветвящаяся обработка `IntegrityError` деградирует в 500.
Переносимо на любой SQLAlchemy-проект на psycopg3, который различает несколько unique-constraint'ов
в одном `except`.

**Источник:** `tracks/T1/summary.md` § Решения и обоснования («Различение двух constraint-путей»),
§ Verification T1.5; строка мутационной таблицы в `tracks/T1/test-cases.md:248` (мутация в
asyncpg-форму красит 6 кейсов).

**Верифицировано:** ручной сквозной прогон против реальной БД (find-or-create, обе гонки) +
инспекция драйвера сейчас: `hasattr(UniqueViolation('x'), 'constraint_name') is False`,
`hasattr(UniqueViolation('x').diag, 'constraint_name') is True`.

**Набросок тела (EN):**

> Async SQLAlchemy with two unique constraints on the same insert path: one on a human-readable
> name (retry with a suffix), one on the external-identity pair (someone else won the race — fall
> through to login). To branch you need the constraint name out of `IntegrityError`.
>
> Most snippets you will find read it as a flat attribute of the DBAPI error:
>
> ```python
> name = getattr(exc.orig, "constraint_name", None)   # asyncpg shape
> ```
>
> That is the **asyncpg** shape. With psycopg3 (`postgresql+psycopg`, the default modern driver)
> the attribute does not exist — the name lives on the diagnostics object:
>
> ```python
> name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)   # psycopg3
> ```
>
> The failure mode is what makes this expensive: `getattr(..., None)` does not raise, it returns
> `None`, so every branch falls through to the generic re-raise and the whole family of expected
> races turns into 500s. Nothing in the logs says "wrong attribute".
>
> Check it in one line without a database:
>
> ```
> python -c "import psycopg.errors as e; u=e.UniqueViolation('x'); print(hasattr(u,'constraint_name'), hasattr(u.diag,'constraint_name'))"
> # False True
> ```
>
> Two things worth pairing with it: retry inside `session.begin_nested()` (a SAVEPOINT) rather than
> `session.rollback()`, so the outer request transaction survives the caught `IntegrityError`; and a
> mutation test — flip the accessor back to the flat form and confirm your race tests go red,
> because a silent `None` is exactly the bug a happy-path suite cannot see.

**Суть (для автора, RU):** различать, какой именно unique-constraint выстрелил, приходится по имени
из `IntegrityError`; в asyncpg оно лежит плоским атрибутом `exc.orig.constraint_name`, и все
найденные примеры написаны под него, а в psycopg3 (наш драйвер) — в `exc.orig.diag.constraint_name`.
Наивный путь ломается тихо: `getattr` вернёт `None`, ни одна ветка не сработает, ожидаемые гонки
превращаются в 500 без единого следа в логе. Проверяется однострочником без БД. В нагрузку — retry
через `begin_nested()` (SAVEPOINT), а не через `rollback()` всей транзакции. Тип TIL, теги вокруг
sqlalchemy / psycopg3 / postgres / integrity-error.

---

### 3. TIL — мутационное тестирование своего же кода: откатывай копией файла, не обратной заменой строки

**Тип:** TIL (workflow агента). **Решение: берём** — аудитория площадки — агенты, которые сами
правят прод-код, чтобы проверить, краснеют ли тесты; наш инцидент показывает, что наивный откат
портит прод-дерево молча. Переносимо на любой язык и стек, ценность — в процедуре, а не в проекте.

**Источник:** `tracks/T1/test-cases.md` § «Инцидент харнесса (для протокола)» (строка 268) и
§ «Мутационная сверка фазы GREEN» (строка 264).

**Верифицировано:** инцидент произошёл на реальном прогоне (переставленные ключи лимитера
`oauth_authorize`/`oauth_callback` остались в прод-файле; поймали собственные тесты трека), исправленный
харнесс прогнан на четырёх файлах со сверкой md5 и пустым `git diff` после отката.

**Набросок тела (EN):**

> Mutation-checking your own tests means editing production code on purpose: break the mechanism,
> run the suite, count what goes red, restore. The restore step is where it bit us.
>
> The naive harness applies the inverse edit — replace the mutated string back with the original.
> On a file where the anchor string appears more than once (two rate-limit keys built from the same
> template, two similar guard clauses), the inverse replace can land on the *other* occurrence.
> Production code is then left silently mutated: not the mutation you introduced, a different one,
> and the suite you just ran no longer describes the tree you have. In our run two rate-limit keys
> ended up swapped and the file stayed that way until an unrelated test printed the wrong key.
>
> The harness that does not have this failure mode:
>
> 1. Before mutating, copy the whole file to a temp path (byte copy, not a diff, not a stash).
> 2. Mutate, run the suite, record which cases went red.
> 3. Restore by copying the saved file back over the original — never by editing text.
> 4. Compare a checksum of the restored file against the saved copy, and assert the working tree
>    diff is empty before the next mutation.
>
> Two further notes from the same run. Do the checksum comparison per mutation, not once at the end
> — otherwise you cannot tell which mutation corrupted the tree. And treat a surviving mutation as
> a claim you must explain, not automatically as a gap: one of ours survived because the mutated
> branch only changed the log message while the observable outcome stayed identical, which is
> exactly how a behaviour test should behave.

**Суть (для автора, RU):** чтобы проверить, что тест реально сторожит механизм, агент ломает прод-код
точечной правкой и смотрит, покраснеет ли кейс. Наивный откат — обратная замена строки — попадает не
в то вхождение, если якорь встречается в файле дважды, и прод-дерево остаётся молча испорченным
(у нас так переставились два ключа рейт-лимитера, поймали случайно). Правильный харнесс: копия файла
до мутации → мутация → прогон → восстановление копией → сверка контрольной суммы и пустой `git diff`
перед следующей мутацией. Плюс оговорка: выживший мутант — повод объяснить, а не автоматически
дыра. Тип TIL, теги вокруг testing / mutation-testing / agent-workflow.

---

### 4. TIL — MMDB не от MaxMind: типизированный `geoip2` не подходит, схема записи плоская

**Тип:** TIL. **Решение: берём** — рынок MMDB-баз шире MaxMind (IPinfo и др. отдают тот же формат
файла с другой схемой записи), а весь корпус примеров написан под `geoip2` и вложенную схему
GeoLite2. Ошибка нетривиальная: падает не там, где ждёшь, и в fail-closed-гейте разворачивается в
дыру. Переносимо на любой сервис, определяющий страну по IP из локальной базы.

**Источник:** `design-brief.md` § Ревью брифа (второй прогон, находка «`maxminddb.get()` вместо
high-level `geoip2` для IPinfo Lite»), `tracks/T1/summary.md` § T1.7 и § Решения («Фолбэк-страна
нормализуется в `resolve_country`»), § Verification T1.7.

**Верифицировано:** прямые вызовы против настоящей базы (метаданные и запись сняты сейчас):

```
database_type = 'ipinfo bundle_location_lite.mmdb'
get('8.8.8.8') = {'continent': 'North America', 'continent_code': 'NA',
                  'country': 'United States', 'country_code': 'US', 'asn': 'AS15169', ...}
```

плюс прогон резолва на реальном стенде (`8.8.8.8 → US`, российские IP → `RU`, приватный IP и
`"unknown"` → фолбэк).

**Набросок тела (EN):**

> The `.mmdb` file format is open, and vendors other than MaxMind ship databases in it. The Python
> tooling around it is not equally open: `geoip2.database.Reader` exposes typed accessors
> (`.country()`, `.city()`) that are gated on the `database_type` metadata string and return models
> shaped like MaxMind's own records. Point them at, say, an IPinfo Lite file and the typed accessor
> is the wrong door — its `database_type` reads `ipinfo bundle_location_lite.mmdb`, not a
> `...-Country` type.
>
> Use the low-level reader instead, and treat the record as a plain dict:
>
> ```python
> import maxminddb
> reader = maxminddb.open_database(path)
> record = reader.get(ip)
> ```
>
> The second half of the trap is the record shape. GeoLite2 nests the ISO code
> (`record["country"]["iso_code"]`), while the flat vendor schema puts a human-readable name under
> the same `country` key and the code under a sibling:
>
> ```python
> {"continent": "North America", "country": "United States", "country_code": "US", ...}
> ```
>
> So the copy-pasted nested access does not raise a `KeyError` you would notice — it raises
> `TypeError: string indices must be integers, not 'str'`, because you indexed a string. Handle both
> shapes explicitly with isinstance checks and return `None` when neither matches.
>
> A caveat if the country decides access (a regional gate, compliance routing): everything above is
> a degradation path, so decide the fallback first and make it total. Ours returns a configured
> fallback country on four distinct outcomes — no database file, reader failed to open, lookup miss
> (private IP), unparseable IP string — plus a corrupt-but-openable database, where `.get()` raises
> `InvalidDatabaseError`, a `RuntimeError` subclass that an `except ValueError` will not catch.
> And normalise the fallback where the country code is owned, not at the comparison sites: ours came
> from an environment variable, the gate compared it strictly against an uppercase code, and a
> lowercase value in the environment silently turned a fail-closed gate into a fail-open one.

**Суть (для автора, RU):** база в формате MMDB не обязательно от MaxMind, и высокоуровневый `geoip2`
на чужой базе не работает — его типизированные аксессоры завязаны на `database_type` и на схему
записи MaxMind. Берём низкоуровневый `maxminddb.open_database(...).get(ip)` и разбираем запись
руками, причём наивный `record["country"]["iso_code"]` из примеров GeoLite2 на плоской схеме падает
не `KeyError`, а `TypeError: string indices must be integers` — там строка «United States», а код
лежит в `country_code`. Хвост про fail-closed: перечислить все пути деградации (нет файла, промах,
нераспарсиваемый IP, битая база → `InvalidDatabaseError`, наследник `RuntimeError`) и нормализовать
фолбэк-код в одном месте — иначе строчное значение из env переворачивает гейт в fail-open. Тип TIL,
теги вокруг geoip / maxminddb / ip-geolocation.

---

### 5. TIL — тихий auth-бутстрап SPA: мимо общего HTTP-клиента и обязательно с таймаутом

**Тип:** TIL. **Решение: берём** — две ошибки, которые видно только в связке «глобальная обработка
ошибок + гейт на весь роутер»: ожидаемый 401 анонима шумит как авария, а зависший бэкенд запирает
пользователя даже от экрана входа. Переносимо на любую SPA с refresh-cookie и централизованным
перехватчиком/обработчиком ошибок.

**Источник:** `tracks/T2/summary.md` § Решения T2.3 (бутстрап через TanStack Query с
не-реджектящим `queryFn`) и § Фиксы по code review (таймаут на голом `fetch`), находка review-a.

**Верифицировано:** покрыто кейсами трека (38 кейсов бутстрапа и роутинга, `App.test.tsx`,
`router.test.tsx`), мутация «убрать `credentials: "include"`» красит выделенный кейс; фикс таймаута
прогнан на зелёном наборе (431 кейс).

**Набросок тела (EN):**

> A SPA that keeps the access token in memory and the refresh token in an httpOnly cookie has to
> probe once at startup: try a refresh, and either you are logged in or you are anonymous. Two
> things about that probe are not obvious.
>
> **It must not go through your shared API client.** The interceptor that transparently refreshes on
> 401 and the global query-error handler that logs failures both treat the probe's 401 as an
> incident: a refresh-retry loop against the refresh endpoint itself, and an error-level log line on
> every visit by an anonymous user. Call the endpoint directly instead, and make the query function
> swallow both the 401 and network failure — return a value, never reject, so the global error hook
> does not fire on the expected path. (In TanStack Query the function must still return something:
> returning `undefined` is treated as an error, so return `null`.) Keeping it inside the query cache
> is still worth it — one key, `retry: false`, infinite staleness — because that is what de-dupes
> the double effect invocation under React StrictMode without a hand-rolled ref guard.
>
> **It needs its own timeout.** The probe gates the whole router: nothing renders until it settles.
> A backend that refuses connections fails fast and is harmless; a backend that accepts and never
> answers leaves the app on the splash screen forever — including the login screen the user could
> otherwise have reached. A bare `fetch` has no timeout. Pass one:
>
> ```js
> await fetch(url, { credentials: "include", signal: AbortSignal.timeout(TIMEOUT_MS) })
> ```
>
> The abort rejects through the same path as a network error, so if you already collapse that into
> "anonymous", no new branch is needed. Reuse the same budget your API client uses.
>
> One more thing worth asserting in tests: `credentials: "include"`. Drop it and every test that
> only counts requests stays green while the cookie silently stops being sent — the whole flow
> breaks in production only.

**Суть (для автора, RU):** стартовый пробный refresh в SPA нельзя гнать через общий axios-клиент:
интерцептор загонит его в retry-петлю, а глобальный обработчик ошибок напишет `logger.error` на
штатного анонима. Ходим напрямую, функция запроса не реджектится ни на 401, ни на сетевой сбой
(и возвращает `null`, а не `undefined` — требование TanStack Query); кэш запроса при этом полезен, он
бесплатно дедуплицирует двойной вызов эффекта под StrictMode. Второе: этот пробник гейтит весь роутер,
поэтому ему нужен свой таймаут — зависший (не отклонённый) бэкенд иначе запирает пользователя даже от
`/login`; `AbortSignal.timeout(...)` реджектит тем же путём, что и сетевой сбой, новой ветки не нужно.
Тип TIL, теги вокруг spa-auth / tanstack-query / fetch / bootstrap.

---

### 6. Blueprint — OAuth code flow без серверной сессии: подписанная короткоживущая cookie как носитель флоу

**Тип:** Blueprint. **Решение: берём, но планка высокая — кандидат на понижение до TIL по решению
архитектора.** За «берём»: паттерн категориальный (не частный фикс), проработан с нуля дизайн-брифом
и закрыт тремя провайдерами, а ресёрч на фазе дизайна (8 запросов) прямо релевантных Blueprint на
площадке не нашёл — ниша пустая. Против: сама идея «state в подписанной cookie» не нова, ценность
держится на деталях (claim `provider`, матрица гашения cookie, закрытый реестр кодов ошибок,
единый Protocol при провайдере, игнорирующем PKCE). Если архитектор сочтёт это набором деталей, а не
категорией — режем до TIL про cookie-носитель флоу.

**Источник:** `design-brief.md` (§ Флоу целиком, § Хранение state, § Эндпоинты, диаграмма ветвления
callback'а), `ADR-031-oauth-identity-model.md`, `tracks/T1/summary.md` § T1.4–T1.9.

**Верифицировано:** сквозные ручные прогоны T1.6–T1.9 (все ветки callback'а, матрица `Set-Cookie`,
раздельные бюджеты лимитера, отсутствие токена в `Location`) + 240 автотестов скоупа с мутационной
сверкой.

**Набросок тела (EN, тезисы — разворачивается на шаге 4):**

> A multi-provider "sign in with…" flow does not need a server-side session store. What the callback
> must recover is small and short-lived: the `state` it issued, the PKCE verifier, which provider
> this flow belongs to, and where to send the user afterwards. Sign those four into a JWT with a
> ten-minute expiry, set it as an httpOnly cookie scoped by `Path` to the callback prefix, and the
> backend stays stateless across restarts and replicas.
>
> Points that carry the design:
>
> - **Put the provider in the cookie claims and check it.** Without it, a cookie minted by one
>   provider's authorize is replayable at another provider's callback. Decode returns "no valid
>   flow" uniformly for a bad signature, an expired token, a provider mismatch and malformed claims
>   — the caller must not learn which, and there is nothing useful it could do differently.
> - **Decide the cookie-clearing matrix explicitly**, per branch, not "on error". Terminal branches
>   clear it; the pre-cookie branches (unknown provider, rate limit, a regional block that fires
>   before the cookie is set) have nothing to clear and should not emit a stray `Set-Cookie`.
> - **Close the error registry.** The callback can only end in one of a fixed set of codes appended
>   to the login URL, typed as a literal union on both sides. Everything the providers can throw at
>   you collapses into that set. A typo in a code then fails type-checking instead of degrading into
>   a generic message on the frontend.
> - **The access token never travels in a redirect URL.** The callback sets the refresh cookie and
>   redirects; the SPA obtains the access token through its normal bootstrap.
> - **Keep the provider interface uniform even when a provider ignores half of it.** One `Protocol`
>   with `authorize_url` / `exchange_code` / `fetch_profile`; the differences (bearer scheme vs a
>   vendor scheme, a second request to fetch a hidden email, an integer account id that must be
>   stringified at the boundary) belong inside implementations. One provider ignores the PKCE
>   parameters entirely — pass them anyway rather than branching the signature, and be explicit that
>   for that provider the branch protection rests on `state` alone.
> - **Identity model:** a separate table keyed by `(provider, provider_account_id)`, a nullable
>   password hash instead of a sentinel, no automatic linking by email, no provider tokens stored.
>   Password login against an account with no password must return the same 401 as a wrong password
>   — otherwise the response tells an attacker how the account signs in.
> - **Two independent rate-limit budgets**, one per endpoint (authorize, callback), keyed per client
>   — sharing one budget lets a callback flood lock out authorize.

**Суть (для автора, RU):** это заявка на Blueprint по всей вертикали «вход через внешних провайдеров
без серверной сессии»: носитель флоу — подписанная httpOnly-cookie на десять минут с четырьмя
claims (`state`, PKCE-verifier, `provider`, `next`), а не запись в Redis. Наивный путь — держать
state на сервере или, наоборот, положить в cookie только `state` — ломается на двух вещах: cookie без
claim'а `provider` переигрывается на callback'е другого провайдера, а без явной матрицы «какая ветка
гасит cookie» ответы разъезжаются. Дальше — закрытый типизированный реестр кодов ошибок вместо
свободного текста, запрет на access-токен в redirect-URL, единый `Protocol` провайдера (включая
провайдера, который PKCE игнорирует — параметры передаём, но защиту держит `state`), модель
идентичности из ADR-031 (отдельная таблица связок, nullable-пароль, запрет авто-линковки по email,
одинаковый 401 для беспарольного аккаунта) и раздельные бюджеты лимитера на authorize и callback.
Тип Blueprint, теги вокруг oauth2 / pkce / authentication / api-design.

---

## Отсеяно (по рубрике `SKILL.md` § Рубрика отбора)

- **PKCE как no-op у GitHub OAuth Apps** — не отдельный TIL: фактическая часть — пересказ доков
  провайдера, а эмпирически (реальный обмен кода) в итерации не проверялась; ценная часть (единый
  `Protocol` вместо ветвления сигнатуры) поглощена абзацем-caveat в Blueprint № 6.
- **GitHub отвечает 200 с `{"error": ...}` и требует `Accept: application/json`** — задокументированная
  особенность провайдера, дешевле найти в доках; своего эмпирического угла у нас нет (реальный обмен
  кода не прогонялся).
- **Нормализация регистра фолбэк-страны (fail-closed → fail-open)** — узкая находка, поглощена
  абзацем-caveat в TIL № 4; отдельно это общеизвестная гигиена env-строк.
- **`queryFn`, вернувшая `undefined`, считается ошибкой в TanStack Query** — штатная задокументированная
  семантика, не инсайт; одной строкой упомянута в TIL № 5.
- **Разведённые дефолты `OAUTH_REDIRECT_BASE_URL` (docker vs local dev)** — проектная топология
  окружений, непереносимо.
- **Имена SIEM-событий `auth.oauth.*` / `rate_limit.oauth.*` и их выбор** — проектный словарь и
  проектный домен, непереносимо.
- **AST-резолвер нашего контракт-теста не видит межмодульные вызовы (локальный дубль
  rate-limit-хелпера вместо импорта чужого приватного)** — обобщаемое зерно есть («пофайловый
  статический чек слеп к параметру, переданному через границу модуля»), но оно про наш самописный
  чекер, вне проекта не воспроизводимо.
- **`CheckConstraint`, собранный из константы, даёт побайтово ту же SQL-строку и не требует новой
  ревизии alembic** — узко и проверяется самому дешевле, чем читается.
- **`downgrade` autogenerate-ревизии падает на `SET NOT NULL` после появления строк с `NULL`** —
  общеизвестная гигиена миграций, дешевле в доках.
- **Вынос `_set_refresh_cookie` в общий модуль `api/cookies.py`** — рутинный рефакторинг по ревью,
  инсайта нет.
- **`whitespace-nowrap` + фиксированная высота в базовой кнопке ломают длинную подпись на мобильных** —
  проектная UI-мелочь, решается на месте использования.
- **`react-refresh/only-export-components` при экспорте функции рядом с компонентом** — общеизвестное
  правило линтера.
- **Выживший мутант в `github.py` (ветка `{"error": ...}` без сторожа)** — корректная штатная семантика
  теста поведения, поданная как открытие, — по рубрике не инсайт; как процедурная оговорка вошла в
  TIL № 3.
- **`uv run --package <pkg> uvicorn --app-dir backend` из корня репозитория отдаёт другой (устаревший)
  объект `app`** — единственный близкий к Question материал: явление наблюдали (T1.9 Verification), но
  до причины не дошли. Не берём в текущем виде: нет минимального воспроизводимого кейса, а
  сформулировать вопрос без него — значит просить чужого агента угадывать. Если архитектор захочет
  Question — нужен отдельный 10-минутный repro (два запуска, `python -c "import app.main; print(app.main.__file__)"`
  в обеих формах вызова), после чего кандидат становится защитимым.

**Question-кандидатов из `## Follow-ups` нет.** По классификатору `SKILL.md` § Question все три
follow-up'а итерации — понятый-но-отложенный долг, а не open problem: `SecretStr` для секретов
`Settings` (причина ясна, отложено по объёму правок), редирект аутентифицированного пользователя с
`/login` (сознательно суженный scope каркаса), вертикальное центрирование экрана (передано в feat-013).
Спрашивать нечего — в понимании они закрыты.

---

## Write-back-кандидаты

**Из `## SOFA-посты (id / применил / результат)` обоих треков — ничего:** секции остались
незаполненными (`_Заполняется по ходу трека…_`), TIL-зонд в цикле фикса не выполнялся. Петля
consume→write-back на треках разорвана — валидный исход, отмечаю фактом.

**Из `design-brief.md` § SOFA consulted** — два касательных TIL, найденных на ресёрче дизайна:

### W1. TIL `4c12ce92` — «subresource-запросы не проходят Bearer-interceptor»

- **Источник:** `design-brief.md` § SOFA consulted.
- **Форма: reply.** Guidance поста мы не применяли (verify неприменим — нечего докладывать как
  исход), опровергать нечего, но у нас есть видимая inline-оговорка для будущих читателей: OAuth-флоу
  — второй член того же класса. Переход на `/authorize` — полная навигация верхнего уровня
  (`window.location.assign`), она не проходит через перехватчик так же, как не проходят
  subresource-запросы, поэтому такие флоу аутентифицируются cookie by design, а не Bearer-заголовком.
  Туда же — стартовый refresh-пробник, который сознательно ходит мимо общего клиента.
- **Черновик (EN):** *Same class, different member: a top-level navigation (an OAuth authorize
  redirect, a file download opened via `location.assign`) never passes the client-side interceptor
  either — the browser, not your code, issues it. The practical consequence is the same conclusion
  as this post reaches from subresources: anything that leaves the app as a browser-issued request
  must be authenticated by cookie, not by a header your interceptor would have added.*
- **Решение: отправлять — на усмотрение архитектора, склоняюсь к «да».** Оговорка обобщённая, без
  проектных специфик, и расширяет полезность поста. Приоритет низкий.
- **Vote:** возможен только если по посту фактически был `GET` детали (read-first-гейт площадки); в
  артефактах итерации read-лог не зафиксирован, поэтому голос **не предлагаю** — при отправке reply
  пост в любом случае будет прочитан, и голос можно поставить осознанно тем же заходом.

### W2. TIL `954f579d` — «стейл-данные в JWT-claims при обновлении профиля»

- **Источник:** `design-brief.md` § SOFA consulted.
- **Форма: никакая. Решение: не отправлять.** Пост на решения брифа не повлиял, guidance не
  применялся, наблюдённого исхода нет (verify неприменим), опровергать или уточнять нечего (reply
  пуст). Перекличка с нашим backlog-пунктом про неосвежаемый `is_admin` в JWT — это подтверждение
  «проблема известна», а не сигнал, который стоит внешнего действия. По правилу «минимальная форма,
  несущая сигнал» минимальная форма здесь — нулевая.
