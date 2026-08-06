# Code Review — режим A (качество кода) — feat-010 «Генерация изображений агентом»

Диапазон: `git diff develop...HEAD` (T1 backend `8ae3088`, T2 frontend `c720065`, test-статусы `e5c891a`).
Ревьюер: correctness / сложность / читаемость / поведенческая безопасность / тесты. Read-only.

## Summary

- **Blocker: 0.** Ядро корректно: атомарность записи артефакт+блоб (одна транзакция, провайдер вызывается до `session.begin()`), маппинг ошибок провайдера в типизированные `UpstreamUnavailableError` с верными статусами, скоуп media-endpoint по проекту/юзеру идентичен эталонному `get_artifact`/`download_artifact`, освобождение objectURL через cleanup-эффекты без утечек, `httpx.AsyncClient` закрывается через `async with`. Всё это хорошо покрыто тестами (атомарность + rollback, все ветки error-mapping, cost None/present, langfuse с cost и без).
- **nit / low: 3** (+ 1 тривиальный). Все — робастность к вырожденным ответам провайдера и future-proofing; ни один не блокирует.
- **pre-existing: 0** новых замечаний.

Отдельно проверено и **не является находкой**: возможное «двойное» отображение плейсхолдера и реальной карточки при завершении генерации — исключено порядком событий (`tool_end` эмитится до `artifact_created` в одном выводе tools-ноды, `stream_events.py:37-52`; на фронте `removePendingImage` отрабатывает раньше `addArtifact`, React батчит апдейты).

## Находки

| Severity | Намерение | Файл:строка | Замечание | Предложение |
|----------|-----------|-------------|-----------|-------------|
| low | suggestion | `backend/app/infra/image_generation.py:113-121` (и `:106-110`) | Парс-блок проверяет **наличие** ключей `data[0].b64_json`/`media_type`, но не тип/непустоту значений. При 2xx-ответе с `b64_json: null` вызов `base64.b64decode(None, validate=True)` бросает `TypeError`, а `except binascii.Error` его не ловит (`binascii.Error` ⊂ `ValueError`, не `TypeError` — проверено) — исключение уходит мимо задуманной классификации `image-generation-malformed-response`. Симметрично: `media_type: null` доходит до `PgBlobStorage.put(mime_type=None)` и падает на NOT NULL-колонке уже внутри транзакции (rollback сработает, но это `IntegrityError`, не 502). Требует вырожденного ответа провайдера — отсюда low. | Ловить `TypeError` рядом с `binascii.Error` в base64-блоке, либо валидировать, что извлечённые `b64_json`/`media_type` — непустые `str`, в общем malformed-блоке (он и так ловит `TypeError`). |
| low | question | `backend/app/api/routes/artifacts.py:73-77` | `mime_type` провайдера отдаётся в `Content-Type` без `X-Content-Type-Options: nosniff`. Эксплойтом не является: endpoint под bearer-JWT (не ambient cookie-auth, прямой переход/CSRF не сработает), а на фронте контент потребляется как blob-objectURL в `<img>`, не навигацией. Заметка на будущее (defense-in-depth), т.к. `mime_type` — данные внешнего источника, echo-нутые в заголовок. | По желанию добавить `X-Content-Type-Options: nosniff` в `headers=`; либо осознанно оставить как есть, учитывая модель auth. |
| low | suggestion | `backend/app/models/artifact.py:51` | Новый relationship `blob` не имеет `passive_deletes=True`/`cascade`. `ArtifactRepository.delete` (pre-existing, сейчас не вызывается ниоткуда — проверено grep'ом) делает `session.delete(artifact)`; если удаление артефактов когда-нибудь подключат к image-типу, ORM попытается занулить NOT NULL-FK `artifact_id` у подгруженного блоба **до** срабатывания DB-level `ON DELETE CASCADE`. Латентно, текущими путями не задевается. | При появлении удаления артефактов выставить `passive_deletes=True` на `blob`, чтобы делегировать каскад БД (FK уже `ondelete="CASCADE"`). |
| trivial | suggestion | `backend/app/infra/image_generation.py:96` | Избыточные классы в `except (httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError)`: `TimeoutException` ⊂ `HTTPError`, `ConnectionError` ⊂ `OSError`. Поведение корректно, просто лишние имена. | Можно сократить до `(httpx.HTTPError, OSError)`; не обязательно. |

## Что проверено и признано корректным (без находок)

- **Атомарность / отсутствие частичной записи.** Провайдер вызывается до `session.begin()`; ошибка провайдера → транзакция не открывается. Ошибка внутри транзакции (например, `put`) → rollback обеих строк. Оба инварианта покрыты `test_generate_image_provider_error_writes_nothing` и `test_generate_image_blob_write_failure_rolls_back_artifact`.
- **Ресурсы.** `httpx.AsyncClient` под `async with` (закрывается). objectURL в `ImageViewer`/`ArtifactThumbnail` создаётся в `useEffect`, ревокается в cleanup при смене blob/unmount — утечки нет; кнопка «.png» переиспользует тот же objectUrl, не ревокает его сам (общий cleanup) — корректно.
- **Concurrency.** `pendingImages` в stream-store ключуется по `call_id` — параллельные `generate_image`-вызовы (разные call_id) добавляются/снимаются независимо; `addPendingImage` идемпотентен, `removePendingImage` — no-op на отсутствующем id. React-query дедуплицирует media-fetch между карточкой ленты и вьюером по общему ключу.
- **Скоуп/безопасность media-endpoint.** `service.get_artifact` + ручная проверка `artifact.project_id != project.id` (через `UserProject`, валидирующий владение проектом) — 1:1 с `get_artifact`/`download_artifact`. Ключ API в заголовке `Authorization`, не в теле/логах; тело ошибки провайдера наружу не отдаётся (клиент получает generic detail), в логах — `status_code`/`model`/`exc_info`, без ключа.
- **Cost-учёт.** `cost_details` не подставляется при `usage.cost is None` (не фабрикуется `$0` — покрыто `test_generate_image_langfuse_observation_omits_cost_when_unknown`); в ToolMessage — литерал `unknown`. Langfuse-блок под `contextlib.suppress(Exception)` (деградирует мягко).
- **Регрессии для существующих потребителей.** `stream_events` расширен на `{"create_artifact", "generate_image"}` без смены формы события; форма dict артефакта (`type`→`artifact_type`) та же. `ToolIndicator` подавлена только для `generate_image` (прочие tools — без изменений). Ветка `image` в `ArtifactView` выведена из-под `SHOW_GROUP_B_STUBS`, slides/audio не тронуты.
- **Тесты.** Упадут при реальной поломке (ассерты на observable-контракт: request body, статусы/коды ошибок, наличие/отсутствие строк в БД, payload observation). Ветки error-mapping параметризованы по статусам и malformed-сценариям.

## Осознанные отклонения (зафиксированы в summary, не флагаются)

Раздельная `BlobStorageDep` вместо метода сервиса; три причины 404 с разными `detail`; литеральный `Cache-Control`; собственный PK у `artifact_blobs`; `runtime` как keyword-only; дублирование ~10 строк objectURL между `ImageViewer` и `ArtifactCard` (вне скоупа фазы). Новых аргументов против них нет.
