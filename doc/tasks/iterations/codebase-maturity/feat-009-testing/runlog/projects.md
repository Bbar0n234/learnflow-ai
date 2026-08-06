# S4 — Projects & artifacts · run-log

Скоуп S4 (широкое покрытие: happy + основные ошибки/авторизация). Автор тестов
независим от автора прод-кода. Возобновление после падения прошлого прогона:
тест-файлы уже лежали почти дописанными — осмотрены, сверены с прод-кодом,
достроены до зелёного и типобезопасности, с нуля не переписывались. Битые места
починены точечно (см. «Починенное при возобновлении»).

## Файлы (всё в `backend/tests/projects/`)
- `conftest.py` — локальные фабрики `ThreadViewFactory` и `ArtifactFactory`
  (async-factory-boy по образцу `learnflow_testing.factories`; общий пакет их не
  поставляет), привязка к транзакционной сессии autouse-фикстурой поверх
  `db_session`.
- `fakes.py` — in-memory `FakeProjectRepository`, `FakeArtifactRepository`,
  `FakeMCPServerRepository` (dict-backed, тот же duck-typed интерфейс, что у
  реальных репозиториев) для sociable-unit сервисов.
- `_builders.py` — хелперы `create_owned_project` / `create_other_project` для
  handler-тестов (вынесены из тела тестов; имя без `test_`-префикса, чтобы pytest
  не собирал их как тесты).
- `test_project_service.py`, `test_artifact_service.py` — sociable-unit поверх
  фейков, проверяют результат (объект/ветка/состояние стора), не вызовы.
- `test_project_repository.py`, `test_artifact_repository.py`,
  `test_thread_view_repository.py` — integration против живого Postgres
  (транзакционный откат из замороженного backend harness).
- `test_projects_api.py`, `test_artifacts_api.py` — integration через authed
  `client` (route → service → repo → real PG).

## Покрытые поведения
- **ProjectService**: create возвращает именованный проект; get существующего;
  get отсутствующего → `EntityNotFoundError`; list → (items, total) с фильтром по
  user; update меняет name; update отсутствующего → not-found; delete удаляет и
  чистит mcp-disables; delete отсутствующего → not-found + cleanup НЕ вызван.
- **ArtifactService**: get/get-missing; list → (items, total) с фильтром по
  project; list_by_thread отдаёт только артефакты своего треда.
- **ProjectRepository**: create+get round-trip; get-missing → None; list_by_user
  сортировка по updated_at desc, limit/offset, изоляция чужих; count_by_user
  только свои; update персистит; delete удаляет строку.
- **ArtifactRepository**: create с thread_id и без (null); get-missing → None;
  list_by_project desc + limit/offset + изоляция; count_by_project; list_by_thread
  asc по created_at; set_message_id обновляет только перечисленные; delete.
- **ThreadViewRepository**: create+get; get-missing; list_by_project desc +
  пагинация; count_by_project; user-scoped JOIN `list_recent` (только треды юзера
  + eager-loaded project через contains_eager) + сортировка desc; count_by_user
  через JOIN; update title; touch двигает updated_at; флаг security_blocked
  (mark/read, missing → False); delete; `ON DELETE SET NULL` зануляет
  artifact.thread_id при удалении треда.
- **Projects API**: POST 201 + body (id/created_at/updated_at); POST без name →
  422 problem+json validation-error; GET list envelope `{items,total,limit,offset}`
  только свои; пагинация; limit=0 → 422; GET 200 owner; GET missing → 404
  entity-not-found; GET чужого → 404 «Project not found»; битый UUID → 422; PUT
  200; PUT чужого → 404; DELETE 204 + затем 404; DELETE чужого → 404.
- **Artifacts API**: GET list envelope owned; list чужого проекта → 404; GET
  detail + content; GET missing → 404 entity-not-found; артефакт из другого
  проекта → 404 «Artifact not found»; артефакт под чужим проектом → 404; download
  md → text/markdown + Content-Disposition attachment + тело; download format=txt
  → 422.

## Дубли / инфра
- Реальный Postgres только в repository-integration и под authed `client`
  (REST поверх БД на транзакционном откате). Логика сервисов — на in-memory
  фейках репозиториев (их настоящий коллаборатор по слою — БД — единственная
  болезненная граница). Внешних эффектов с mock нет (`FakeMCPServerRepository` —
  fake-spy через состояние `cleaned_projects`, проверяем результат-эффект, не
  факт вызова).

## Результат верификации
- `make test-scope P=backend/tests/projects` — **65 passed, 1 xfailed**.
- `ruff check tests/projects/` — clean; `mypy backend/` по scope — clean.

## Починенное при возобновлении (только тест-файлы скоупа, прод не тронут)
- `test_artifacts_api.py` импортировал хелперы из `tests.projects.test_helpers`,
  а файл при прошлом прогоне переименован в `_builders.py` (чтобы pytest не
  собирал его как тест) → импорт поправлен на `_builders`.
- Два repo-теста (`set_message_id`, `deleting_thread_nulls_artifact_thread_id`)
  падали с `MissingGreenlet`: `expire_all()` оставляет объект в identity-map
  expired, а последующий `get` лениво рефрешит вне greenlet-контекста. Заменено
  на `expunge_all()` — чистый detach, чтение делает свежий async SELECT.
- `conftest.py`: `factory.Sequence`/`factory.SubFactory` ловили mypy
  `no_implicit_reexport` (factory_boy 3.3.3 шипит py.typed, но не реэкспортит эти
  имена в `__all__`). Импорт переведён на defining-submodule
  `from factory.declarations import Sequence, SubFactory` — не suppression, не
  правка конфига. (Общий `learnflow_testing.factories` использует тот же паттерн
  `factory.Sequence`, но не проверяется `mypy backend/`, т.к. лежит в `packages/`.)

## Баги для Ф5
- **DELETE проекта не идемпотентен** (нарушение api.md §Status codes: «повторный
  DELETE того же ресурса — тоже 204, идемпотентность»). Handler резолвит проект
  через `UserProject` (`get_user_project` → `ProjectService.get_project`), поэтому
  второй DELETE удалённого проекта поднимает `EntityNotFoundError` → 404, а не 204.
  Зафиксировано тестом `test_delete_project_is_idempotent` с
  `@pytest.mark.xfail(strict=True)` — тест станет зелёным (xpass), как только прод
  починят. Прод НЕ правился (A6).

## Непокрытое и почему
- **PDF-ветка download** (`format=pdf`): требует бинарь wkhtmltopdf и
  `app.state.settings.pdf_conversion_timeout_seconds`, который заполняет lifespan;
  под `ASGITransport` lifespan не поднимается (см. docstring `app` в backend
  conftest). MD-путь покрыт; PDF — узкий integration вне дешёвого harness.
- Конкурентные запросы в одном тесте не делались (ограничение одной сессии
  харнесса, F2 в infra.md).
- Edge/negative-глубина (например, гонки, экзотические constraint-нарушения) не
  добиралась: S4 — широкое покрытие, не критпуть для дополнительной глубины
  (критпути — auth/guard/runtime/SSE по testing.md §Глубина).

## Блокеры
- Нет. Замороженную инфру (`packages/testing`, общий `backend/tests/conftest.py`,
  Makefile, pyproject) не трогал; прод-код не правил.
</content>
