# Test Cases: feat-010 — Генерация изображений агентом / трек T2 (Frontend)

Трек T2 оживляет фронтовую часть генерации изображений: настоящая картинка вместо
dev-заглушки. Тесты страхуют **новую фичу** (не поведение-сохраняющий рефактор) и её
контракт с бэкендом (трек T1): media-fetch под JWT → `Blob` → objectURL → `<img>`;
живой `ImageViewer` с состояниями загрузка/готово/404; превью в карточке ленты
`ArtifactCard`; плейсхолдер генерации по SSE `tool_start`/`tool_end` (ключ — `call_id`)
с подавлением пилюли `ToolIndicator` для `generate_image`.

Ожидаемые изменения поведения (в сравнении с прежней заглушкой):

- `ImageViewer` больше не статичная иконка — качает бинарь с
  `GET …/artifacts/{id}/media`, показывает картинку, зум, caption = prompt (`content`),
  скачивание уже полученного blob как `.png`; кнопки «Открыть в окне» больше нет.
- Ветка `type === "image"` в `ArtifactView` выведена из-под `SHOW_GROUP_B_STUBS` в прод;
  slides/audio остаются под флагом.
- `ArtifactCard` для `type === "image"` показывает миниатюру 64×40 с того же
  media-endpoint; прочие типы — прежняя иконка, без media-запроса.
- В ленте на время генерации стоит pending-карточка (`GeneratingArtifactCard`), снимается
  по `tool_end` с тем же `call_id` (в т.ч. при ошибке tool'а); пилюля `ToolIndicator`
  подавлена именно для `generate_image`.

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры** (применять, если итерация их касается): `📊` — проверка наблюдаемости (структура БД, метрики, Redis state, Langfuse); `🔴` — проверка реальных инъекций / атак / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `frontend/src/**`); `*(регресс)*` — кейс страхует «поведение не сломалось».
- **run-log** (только у перепрогнанных кейсов) — строка-история флипов с причиной:
  `runs: r1 ✅ → r2 ❌ (после фикса review #3: регрессия инвалидации) → r3 ✅`.
  Один прогон — run-log не нужен. Перепрогон после правки кода обязателен (см. ре-верификацию).

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check-fe`/`make test-fe`) — перепрогон всегда; ручные/UI-кейсы — перепрогон только затронутой области. Каждый перепрогон → запись в run-log.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики: не сошлось — повтори (мог быть транзиент); не сошлось второй раз — fail + эскалация, без долгой отладки. Инструменты: DevTools Network (media-запрос, SSE-кадры), Console (`@/shared/lib/logger`). Код читать только там, где поведение иначе не наблюдаемо. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer**.

**Скоуп по трекам.** Кейсы с префиксом `{T2.N}` гоняются на треке T2 + Layer 0; cross-cutting (Layer 2/3 без префикса) — в INTEGRATION_TEST.

### Процесс (тестировщик поднимает стенд сам)

1. Инфраструктура: `make docker-up` (полный стек) — нужен реально работающий backend media-endpoint + агент с tool'ом `generate_image` (трек T1). Фронт — `make dev-fe` либо в составе `docker-up`.
2. Акторы через UI register: **user-a** обычный пользователь с проектом.
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в run-log + `## Решения и обоснования` summary трека.
4. Реальное тестирование через UI. После прогона — сводка (pass / failed / **deferred**).

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| Media-запрос / SSE | DevTools → Network (`…/media`, `text/event-stream`) |
| Логи фронта | DevTools → Console (через `@/shared/lib/logger`) |

---

## Дизайн автотестов

Все автотесты трека — colocated Vitest в `frontend/src/**`, 30 новых кейсов; стек — Vitest + jsdom + RTL + MSW, свежий `QueryClient` с `retry:false`, Zustand-сброс между тестами.

**Покрываем автотестом** — по записи на суиту:

### `artifacts.test.ts` — API-слой media

1. **Файл**: `frontend/src/shared/api/artifacts.test.ts` — integration (MSW) + solitary-unit для предиката
2. **Тестирует**: `shared/api/artifacts.ts :: getArtifactMedia, useArtifactMedia, isArtifactMediaNotFound`
3. **Суть**: хук скачивает картинку с media-endpoint как `Blob` и не стреляет запросом,
   пока нет id; 404 всплывает ошибкой, которую предикат надёжно отличает от любых других сбоев.
4. **Кейсы**:
   - `getArtifactMedia`/`useArtifactMedia` качают `Blob` (mime из `Content-Type`)
   - `enabled` не стреляет при отсутствии id (idle, без запроса)
   - 404 всплывает ошибкой, которую распознаёт предикат
   - `isArtifactMediaNotFound`: 404 → true; 500 / не-Axios / null → false

### `ImageViewer.test.tsx` — вьюер изображения

1. **Файл**: `frontend/src/pages/artifact/ui/ImageViewer.test.tsx` — integration
2. **Тестирует**: `pages/artifact/ui/ImageViewer.tsx`
3. **Суть**: вьюер проводит пользователя через все состояния — шиммер во время загрузки,
   картинка с подписью, внятные пустые состояния на 404 и на сбой — и не течёт памятью
   (objectURL освобождается). Скачивание отдаёт уже загруженный blob без второго запроса.
4. **Кейсы**:
   - загрузка: шиммер `aria-label="Изображение загружается"`
   - готово: `<img>` с `alt` = prompt, `src` = objectURL, caption = prompt
   - 404: «изображение не найдено», зум-pill скрыт, `.png` задизейблена; 500: «не удалось загрузить изображение»
   - скачивание: `.png` активна только в «готово», `download` = `<title>.png`, `href` — тот же objectURL (без второго запроса)
   - objectURL ревокается на unmount

### `ArtifactCard.test.tsx` — карточка артефакта

1. **Файл**: `frontend/src/pages/chat/ui/ArtifactCard.test.tsx` — integration
2. **Тестирует**: `pages/chat/ui/ArtifactCard.tsx`
3. **Суть**: карточка image-артефакта показывает живое превью и ведёт на детальный роут;
   остальные типы получают иконку и ни одного лишнего сетевого запроса; битое превью
   грациозно падает на иконку, не ломая кликабельность.
4. **Кейсы**:
   - image: превью с media-endpoint (objectURL → `<img>`), карточка = Link на детальный роут
   - non-image: иконка `FileText`, media-запроса нет (MSW `onUnhandledRequest:"error"` подтверждает)
   - 404: фолбэк на иконку (svg, не битый `<img>`), карточка кликабельна
   - objectURL ревокается на unmount

### `GeneratingArtifactCard.test.tsx` — плейсхолдер генерации

1. **Файл**: `frontend/src/pages/chat/ui/GeneratingArtifactCard.test.tsx` — unit
2. **Тестирует**: `pages/chat/ui/GeneratingArtifactCard.tsx`
3. **Суть**: плейсхолдер доступен скринридеру как статус и сообщает, что идёт генерация.
4. **Кейсы**:
   - `role="status"` с именем «Идёт генерация изображения», текст «Генерирую изображение…»

### `MessageList.test.tsx` — лента сообщений

1. **Файл**: `frontend/src/pages/chat/ui/MessageList.test.tsx` — integration
2. **Тестирует**: `pages/chat/ui/MessageList.tsx`
3. **Суть**: на каждую активную генерацию лента показывает ровно одну pending-карточку
   и прячет для неё tool-пилюлю; для остальных tool'ов пилюля живёт как раньше.
4. **Кейсы**:
   - одна pending-карточка на каждый `call_id` из `pendingImages`
   - `ToolIndicator` подавлен для `activeTool === "generate_image"`, рендерится для прочих (`web_search`)
   - без активных генераций плейсхолдеров нет

### `stream-store.test.ts` — стор стрима (дополнение)

1. **Файл**: `frontend/src/stores/stream-store.test.ts` — unit, дополнение к существующему файлу
2. **Тестирует**: `stores/stream-store.ts :: addPendingImage, removePendingImage`
3. **Суть**: реестр активных генераций не накапливает дублей и мусора — добавление
   идемпотентно, удаление неизвестного id безопасно, старт и конец стрима сбрасывают
   состояние.
4. **Кейсы**:
   - `addPendingImage` идемпотентен (без дублей)
   - `removePendingImage` — no-op на неизвестный id
   - `startStream`/`endStream` сбрасывают `pendingImages`

### `useAgentStream.test.ts` — обработка SSE (дополнение)

1. **Файл**: `frontend/src/pages/chat/model/useAgentStream.test.ts` — integration, live SSE через MSW, дополнение к существующему файлу
2. **Тестирует**: `pages/chat/model/useAgentStream.ts`
3. **Суть**: события генерации двигают реестр pending-картинок — `tool_start` ставит
   плейсхолдер, `tool_end` снимает, в том числе когда tool завершился ошибкой; чужие
   tool'ы реестр не трогают.
4. **Кейсы**:
   - `tool_start(generate_image)` → добавляет `call_id` в `pendingImages`
   - `tool_end` с тем же `call_id` → снимает (в т.ч. при завершении tool'а с ошибкой — эмуляция того же `tool_end`)
   - non-image tool (`web_search`) `pendingImages` не трогает; `activeTool` работает как раньше *(регресс)*

**Осознанно не покрываем автотестом** (что — почему — куда уехало):

- **Пошаговый зум** (`ZOOM_STEPS`, кнопки +/−/«По ширине») — предсуществующая UI-логика заглушки, не изменена в feat-010; автотест покрывает только релевантную новинку (видимость pill в «готово» vs скрытие в 404) → ручной хвост, визуальная сверка с мокапом.
- **Реальное скачивание файла на диск** — jsdom не сохраняет файлы; тест проверяет корректность собранного anchor (`download`, `href`), но не факт «файл лёг в загрузки с картинкой внутри» → вручную / E2E (👤).
- **Дедупликация сети между карточкой ленты и вьюером одним media-ключом** — внутреннее поведение react-query (общий `queryKey` + `staleTime: Infinity`), в изоляции компонента потребитель один; unit-тест проверял бы библиотечную механику → живой стенд, DevTools Network — кейс `{T2.7}` / Layer 2.
- **Визуальная параметрия с мокапом и тёмная/светлая тема** — вне возможностей jsdom (нет layout/CSS), классический ручной хвост приёмки UX → 👤 ручные кейсы; browser-e2e и visual-regression — backlog проекта (headless к HTTPS в облаке не работает — `testing.md` § Frontend).
- **`ArtifactView` type-dispatch и раз-гейт `SHOW_GROUP_B_STUBS`** — `SHOW_GROUP_B_STUBS = import.meta.env.DEV`, в vitest всегда true, unit-тест не отличит прод от dev по флагу; сам `ImageViewer` покрыт напрямую → чтение кода (`ArtifactView.tsx:45-58`) + ручной кейс на прод-сборке.

**Замеченные прод-баги (для fixer'а):** нет. Реализация трека соответствует контракту design-brief; наблюдаемое поведение багов не показало.

### Layer 0: Automated gate

- [x] `make check-fe` — ESLint (+ FSD-boundaries) + Prettier `--check` + `tsc -b` strict → **0 ошибок**. (tester r2: перепрогон — зелёный.)
- [x] `make test-fe` — colocated Vitest скоупа зелёные → **151 passed (27 файлов)**, из них 30 новых кейсов по T2. (tester r2: перепрогон — 151 passed, 27 файлов; счётчик приведён к факту после фикса R1, ранее в этой строке стояло 150.)

---

## Ручные кейсы + статусы

> Узкий ручной хвост — то, что не закрыто автотестом (визуальная сверка, реальный
> браузер, сквозной путь через реальный backend+агент). Статусы ведут tester/fixer.

### Layer 1: Трек T2 — Frontend (на живом стенде)

> **Инфра-блокер живого стенда (tester r1).** Стенд feat-010 поднять не удалось: порт
> `8000` занят **чужим backend'ом другого worktree** — в его OpenAPI нет маршрута
> `…/media` (feat-010), схема `/api/auth/login` отличается. Мой `make dev` не забиндил
> `8000` («Address already in use»); vite ушёл на `5174`. По CLAUDE.md § Параллельная
> разработка занятый порт — инфра-конфликт, который я **эскалирую архитектору, а не
> разруливаю** (чужой процесс не убивал, порты не переназначал, свой frontend на `5174`
> остановил за собой). БД (`docker-up-db` на `5432`), миграции и `seed-demo` — мои, подняты
> успешно; сид создаёт image-артефакт `e1704694-…` **без блоба** (media отдаёт 404) — этого
> хватило бы для живого прогона `{T2.4}`/`{T2.5}`(фолбэк)/`{T2.6}`, но без своего backend'а
> на `8000` фронт не к чему подключить. Итог: живые Layer-1 кейсы ниже — 👤 (см. пометки).

- [ ] `{T2.1}` 👤 **Требует ручной проверки архитектором на живом стенде + реально сгенерированной картинке.** Нет реального `LLM_API_KEY` → живьём картинку не сгенерировать, а `seed-demo` кладёт image-артефакт без блоба (media=404), поэтому «готового» состояния с настоящим бинарём мне взять неоткуда; плюс инфра-блокер `:8000`. Что смотреть архитектору: открыть существующий image-артефакт → в DevTools Network `GET …/media` = 200 с `Cache-Control: private, max-age=31536000, immutable` (заголовок подтверждён чтением `backend/app/api/routes/artifacts.py:76`), картинка показана, caption под ней = prompt, в шапке «image · <дата>», кнопки «Открыть в окне» нет (в коде `ImageViewer.tsx` её и импорта `ExternalLink` нет — верифицировано). Логика состояния «готово» зелёная в `ImageViewer.test.tsx` [auto].
- [ ] `{T2.2}` 👤 **Требует человеческих глаз + реальной картинки** (зум по ощущению, кадрирование под разные пропорции). Блок тот же (нет блоба/LLM-ключа + инфра `:8000`). Что смотреть: pill виден в «готово», ступени `50/75/100/125/150/200%` (в коде `ZOOM_STEPS = [50,75,100,125,150,200]`), «По ширине» сбрасывает на 100% (кнопка вызывает `setZoomIndex(2)`); рамка фиксирована `aspectRatio: 4/3` + `object-cover` → кадрирует картинку любых пропорций (16:9/1:1/21:9) в единый бокс. Видимость pill в «готово» vs скрытие в 404 — зелёная [auto]; сами ступени зума осознанно вне автотеста (дизайн-раздел § «Осознанно не покрываем»).
- [ ] `{T2.3}` 👤 **Требует реального blob'а на диск** (jsdom файл не сохраняет — § «Осознанно не покрываем»). Блок тот же. Что смотреть: кнопка `.png` активна только в «готово», клик сохраняет `<title>.png`, файл открывается корректной картинкой; повторного `…/media` в Network нет (в коде `handleDownload` переиспользует уже полученный `objectUrl`, без второго fetch — верифицировано `ImageViewer.tsx:53-62`). Сборка anchor (`download`, `href`=тот же objectURL, без 2-го запроса) — зелёная [auto].
- [ ] `{T2.4}` 👤 **Логика зелёная в автотесте; живой прогон на реальном backend заблокирован инфра-конфликтом `:8000`.** Сид даёт ровно нужный кейс: image-артефакт `e1704694-…` без блоба → `GET …/media` = **404** (подтверждено curl'ом напрямую к маршруту `artifacts.py:69-70` возвращает 404 при `blob is None`). Ожидаемое: вьюер показывает пустое состояние «изображение не найдено», зум-pill скрыт, `.png` задизейблена, не бесконечная крутилка (`ImageViewer.tsx:100-108,118` — условный рендер `isEmpty`). Состояние 404-пусто + скрытие pill + дизейбл `.png` покрыто `ImageViewer.test.tsx` [auto]. Для живого подтверждения архитектору: поднять feat-010 backend на свободном `:8000`, войти demo/demo-pass-1234, открыть артефакт `e1704694-dae2-4a09-9c16-d16609464687` (проект `c89151de-…`).
- [ ] `{T2.5}` 👤 **Частично seed-testable, но заблокировано инфра `:8000`; «настоящая миниатюра» дополнительно требует блоба.** Миниатюра 64×40 с реальным изображением — нужен блоб (нет). Фолбэк-ветка (404 → иконка `ImageOff`, не битый `<img>`, карточка кликабельна) — воспроизводима на сид-данных, но живьём не прогнана из-за `:8000`. Фолбэк на иконку при 404 + клик-навигация — зелёные в `ArtifactCard.test.tsx` [auto].
- [ ] `{T2.6}` 👤 *(регресс)* **Seed-testable, живой прогон заблокирован инфра `:8000`.** Сид даёт много не-image артефактов (summary/plan/outline/code); в чат-ленте карточка — только inline summary (linked-артефакт), image-артефакт стоит standalone в списке артефактов. Ожидаемое: не-image карточки — иконка `FileText`, `…/media`-запроса по ним нет (в коде `ArtifactCard.tsx:21-25` `useArtifactMedia` вызывается только для `isImage`). «non-image → нет media-запроса» жёстко покрыто `ArtifactCard.test.tsx` (MSW `onUnhandledRequest:"error"`) [auto].
- [ ] `{T2.7}` 👤 📊 **Требует реального 200-блоба + браузер-Network** (внутренняя механика react-query dedup + disk-cache — § «Осознанно не покрываем»). Блок тот же. Что смотреть: media-запрос один на пару «карточка+вьюер», один `…/media` 200, повторный — `(disk cache)`/отсутствует. Общий media-ключ подтверждён чтением: и `ArtifactCard.ArtifactThumbnail`, и `ImageViewer` зовут `useArtifactMedia(projectId, artifactId)` по одному ключу `queryKeys.projects.artifactMedia` (`artifacts.ts:122-132`).
- [x] `{T2.8}` *(регресс)* **Verified (code-inspection + прод-бандл).** Ветка `image` в `ArtifactView.tsx:45-55` вне флага (`if (type === "image")` без `SHOW_GROUP_B_STUBS`), slides/audio — под `SHOW_GROUP_B_STUBS` (строки 42, 56). `SHOW_GROUP_B_STUBS = import.meta.env.DEV` → в любой `vite build` статически `false`. Прогон: `vite build` собрался; grep бандла — строки `ImageViewer` **присутствуют** («изображение не найдено», «не удалось загрузить изображение»), UI-строки slides/audio-вьюеров («Заметки агента», «Транскрипт») **отсутствуют** (dead-code eliminated) → в проде `image` рендерит `ImageViewer`, slides/audio падают в дефолтный markdown-viewer. Что осталось архитектору (👤, опц.): визуально глянуть один прод-роут в браузере — но факт гейтинга доказан бандлом.

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [x] Плейсхолдер генерации: **SSE-каркас, на котором держится плейсхолдер, подтверждён живьём** (INTEGRATION_TEST, backend :8010, реальная генерация). В потоке пришли `tool_start(tool=generate_image, call_id=call_3fa34e3a…)` → `tool_end(тот же call_id)` → `artifact_created(artifact_type=image)` в этом порядке — фронт добавляет pending-карточку по `call_id` из `tool_start` и снимает по совпадающему `call_id` из `tool_end`, реальную ставит по `artifact_created`; совпадение `call_id` (ключ добавления/снятия) проверено. Сам рендер pending-карточки (шиммер, «Генерирую изображение…», indeterminate-бар), подавление пилюли `ToolIndicator` и снятие плейсхолдера — фронт-логика, покрыта `MessageList.test.tsx`/`useAgentStream.test.ts`/`stream-store.test.ts` [auto]; визуальная сверка в браузере — в Layer 3 ниже (👤).
- [x] Плейсхолдер не зависает при ошибке tool'а: **подтверждено живьём.** Спровоцировали реальный сбой генерации (агент передал невалидный `resolution` → OpenRouter **400** → `UpstreamUnavailableError` code=`image-generation-failed`, `infra/image_generation.py:86`; 400 не тарифицируется). В SSE-потоке пришли `tool_start(generate_image, call_id=call_66c10e91…)` → `tool_end(тот же call_id)` **без** `artifact_created` — т.е. `tool_end` эмитится и на ошибке (плейсхолдер снимается, не виснет), реальная карточка не встаёт. БД: ни новых `artifacts`, ни `artifact_blobs` — сбой не пишет ничего (all-or-nothing подтверждён и на живом слое, ср. `{T1.3}`).
- [x] *(регресс)* Пилюля `ToolIndicator` для прочих tool'ов (`web_search` и т.п.) отображается как раньше — подавление точечное только для `generate_image`. Само подавление — чисто фронтовое (условие рендера в `MessageList.tsx`: `activeTool !== "generate_image"`), нет backend-поверхности для живого прогона; мутационно-чувствительно покрыто `MessageList.test.tsx` [auto] (`web_search` → пилюля рендерится, `generate_image` → подавлена). Живой слой подтверждает лишь, что не-image tool'ы шлют обычные `tool_start`/`tool_end` без изменения формы события (маппер `stream_events.py` расширен только на имя `generate_image`, ветка прочих tool'ов не тронута). Визуальная сверка пилюли — 👤 в Layer 3.

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] 👤 Сквозной путь: пользователь просит «сделай обложку статьи…» → в ленте плейсхолдер → по готовности карточка с реальным превью → клик открывает `ImageViewer` с той же реальной картинкой, зумом, caption = prompt, рабочим скачиванием `.png`. Агент → backend media → карточка+вьюер показывают один и тот же бинарь. **Backend-половина закрыта живьём** (см. T1 Layer 2: генерация → артефакт+блоб → media отдаёт реальный JPEG под immutable-кэшем); осталась визуальная сверка в браузере. Фронт-рендер (плейсхолдер, превью-карточка, вьюер, скачивание) покрыт фронт-автотестами. **Готовый живой артефакт:** войти `tester-1784153640` / `test-pass-1234`, проект `img-test` (`d1ddb38c-2ccc-4d68-9a17-24b0f3c33618`), артефакт `b868312d-8de7-4df4-a21e-99eeff349925` (реальный JPEG, красный круг на белом). Стенд фронта требует прокси API на backend feat-010 (`vite.config.ts` захардкожен на `:8000` — либо поднять feat-010 backend на свободном `:8000`, либо временно переназначить `proxy.target` на `:8010`).

---

## Находки ревью [severity+owner]

> Пишет test-reviewer (adversarial-ревью тестов против контракта, read-only). Чисто — секция пустая.

**Ревью #1 (test-reviewer, adversarial против design-brief §§ Отдача на фронт, Frontend).** Blocker/major нет, [prod] нет.

- R1 minor [test] `stream-store.test.ts:173` — «clears pending images on startStream and endStream» упаковывает два разных триггера (сброс на `startStream` и на `endStream`) в один `it` с двумя act/assert-парами → против § Структура «одно поведение на тест». Фикс: разбить на два теста (или `parametrize`-таблицу «триггер → сброс»). Не влияет на честность, чисто гигиена AAA.
  - **✅ Fixed (GREEN, r1).** Разбит на два теста «clears pending images on startStream» / «…on endStream» — по одному триггеру и AAA-паре на кейс; `test-fe` 151 passed (было 150), `check-fe` зелёный.
- R2 minor [test] `ArtifactCard.test.tsx:60,61,87,106,107,121` — запросы через `container.querySelector("img"/"svg")`, ниже приоритета RTL (§ Frontend «не лезем в container.querySelector»). Оправдано: миниатюра декоративна (`alt=""`, `aria-hidden` в `ArtifactCard.tsx:63,71`) — доступной роли нет, querySelector тут legitimate last-resort. Мутационно-чувствителен (assert упал бы при регрессии), false-green нет. Фикс не обязателен; при желании — `data-testid` на обёртке миниатюры.
  - **Accepted (wontfix, r1).** По решению ревьюера querySelector — legitimate last-resort для декоративной миниатюры без доступной роли; false-green нет, фикс не обязателен. Закрыта без изменения кода.

Чисто (проверено против контракта и §§ Чек-лист ревьюера / Целостность):
- **MSW-фейк не лжёт контракту.** media-URL `/api/projects/p1/artifacts/a1/media` совпадает с `apiClient` baseURL `/api` (`client.ts:19`) + путём из design-brief; success-хэндлер отдаёт bytes + `Content-Type: image/png` (mime из `mime_type` — как в контракте), 404 — отдельным статусом. Предикат `isArtifactMediaNotFound` смотрит только на `status===404`, тело 404 роли не играет.
- **Нет false-green на критпутях.** Подавление пилюли `generate_image` (`MessageList.test.tsx:55`) мутационно-чувствительно: убери guard в проде — `ToolIndicator` отрендерит текст «generate_image» и `queryByText` его найдёт → тест падает; web_search-кейс подтверждает, что подавление точечное. 404 vs generic-500 различены и в API-слое (`artifacts.test.ts`), и во вьюере (`ImageViewer.test.tsx:94,114`). Снятие плейсхолдера по `tool_end` независимо от успеха tool'а покрыто (`useAgentStream.test.ts`), non-image tool `pendingImages` не трогает (регресс `activeTool` сохранён).
- **Флак/изоляция.** Свежий `QueryClient` + `retry:false` (`test-utils`), Zustand auto-reset (`setup.ts` `vi.mock("zustand")`), objectURL-стабы переустанавливаются в `beforeEach` каждого файла; `onUnhandledRequest:"error"` ловит незамоканные запросы (гарантия «non-image → нет media-запроса»). Loading-состояние ассертится синхронно на первом рендере — детерминизм не зависит от `delay(50)`.
- **A6 целостность.** Диффы `stream-store.test.ts` и `useAgentStream.test.ts` — чистые добавления (helper-функции + новые `it`), ни один существующий ассерт не удалён и не ослаблен. Чужие тест-файлы (в т.ч. backend `tests/personalization/*` — скоуп T1) в T2-ревью не входят и не трогались.
- **Осознанные непокрытия обоснованы.** `Cache-Control: …immutable` — backend-заголовок, не наблюдаемый во фронт-юнитах (jsdom/MSW), корректно вынесен в ручной `{T2.1}`/`{T2.7}`; download-на-диск, dedup-сети, визуальная параметрия, `SHOW_GROUP_B_STUBS` (= `import.meta.env.DEV`, в vitest всегда true) — вне возможностей jsdom, вынесены в ручной хвост честно.

---

## Покрытие (опционально)

| Поведение / контракт (design-brief §§ Отдача на фронт, Frontend) | Закрывающие кейсы |
|---|---|
| media-fetch под JWT → `Blob`, mime из `Content-Type` | `artifacts.test.ts` (useArtifactMedia success) `[auto]`; `{T2.1}` |
| 404 без блоба ≠ сетевая ошибка (классификация) | `artifacts.test.ts` (isArtifactMediaNotFound, 404-hook) `[auto]`; `{T2.4}` |
| `ImageViewer`: загрузка/готово/404, caption=prompt, зум-pill, `.png` | `ImageViewer.test.tsx` (7 кейсов) `[auto]`; `{T2.1}`–`{T2.4}` |
| `ArtifactCard`: превью image / иконка non-image / фолбэк 404 / без лишнего запроса | `ArtifactCard.test.tsx` (5 кейсов) `[auto]`; `{T2.5}`, `{T2.6}` |
| Плейсхолдер по `call_id`, подавление пилюли `generate_image` | `MessageList.test.tsx` + `GeneratingArtifactCard.test.tsx` + `useAgentStream.test.ts` + `stream-store.test.ts` `[auto]`; Layer 2 |
| revoke objectURL на unmount (нет утечки) | `ImageViewer.test.tsx` / `ArtifactCard.test.tsx` (unmount-кейсы) `[auto]` |
| раз-гейт `image` из-под `SHOW_GROUP_B_STUBS` | `{T2.8}` 👤 (флаг = DEV, автотест не различает прод) |
| дедуп сети карточка+вьюер | `{T2.7}` 👤 (внутренняя механика react-query) |
