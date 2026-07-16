# Implementation Plan: feat-010 / трек T2 — Frontend

## Контекст

Трек T2 оживляет фронтовую часть генерации изображений: настоящая картинка вместо
dev-заглушки. Пользователь просит агента сделать изображение → в ленте на время
генерации стоит плейсхолдер → по готовности встаёт карточка с превью → по клику
открывается `ImageViewer` с реальной картинкой, зумом, подписью и скачиванием.

Всё это T2 реализует **против контракта бэкенда** (трек T1), не против его кода:

- артефакт `type === "image"`, `content` = prompt генерации (он же alt и caption);
- `GET /projects/{project_id}/artifacts/{artifact_id}/media` → bytes, `Content-Type`
  из `mime_type`, `404` если блоба нет, `Cache-Control: private, max-age=31536000, immutable`;
- SSE-события `tool_start` / `tool_end` (поля `tool`, `call_id`) и `artifact_created`
  форму не меняют; маппер T1 лишь расширяется на имя tool'а `generate_image`.

Источники:

- **Tasklist:** `doc/tasks/tasklist-post-mvp.md` → запись `feat-010` (критерии приёмки).
- **Design-brief:** `doc/tasks/iterations/post-mvp/feat-010-image-generation/design-brief.md`
  — разделы «Отдача на фронт», «Frontend», «Промптинг»; границы трека — `## Партиция треков` (T2 = `frontend/src/**`).
- **Мокап (UI-референс, согласован архитектором):**
  `.../mockups/image-artifacts.html` — карточка с превью, плейсхолдер генерации, состояния вьюера.
- **Архитектурная дока:** `doc/tech/frontend.md`, `doc/tech/streaming.md` (SSE-протокол),
  `doc/tech/conventions/frontend.md` (Query vs Zustand, фабрика query-keys, stub-gating, токены).

Файловый скоуп T2 (по партиции): `frontend/src/**` — `pages/artifact/` (ImageViewer + ArtifactView),
`pages/chat/` (ArtifactCard + плейсхолдер, вкл. `model/useAgentStream.ts` и рендер ленты),
`shared/api/artifacts.ts` + `shared/api/query-keys.ts`, `stores/stream-store.ts`. Бэкенд и `configs/` — вне трека.

Текущее состояние кода (сверено grep/чтением):

- `ImageViewer.tsx` — визуальная заглушка (иконка «изображение недоступно», mock-title/caption, кнопка
  «Открыть в окне»), тело картинки не запрашивается.
- `ArtifactView.tsx` — ветка `image` под `SHOW_GROUP_B_STUBS`, рендерит `ImageViewer` с `title`/`createdAt`.
- `ArtifactCard.tsx` — единая карточка с иконкой `FileText`, без учёта типа; используется и в стриме
  (`MessageList`), и в персистентной ленте (`MessageItem`).
- `shared/api/artifacts.ts` — есть `downloadArtifact` (axios blob + JWT-interceptor) как образец; media-фетча нет.
- `useAgentStream.ts` + `stores/stream-store.ts` — `tool_start`→`setTool(tool)`, `tool_end`→`setTool(null)`
  (одиночный `activeTool` для `ToolIndicator`), `call_id` сейчас игнорируется; `artifact_created`→`addArtifact`.

## Фазы

### T2.1: Media-фетч и хук `useArtifactMedia`

**Цель:** появляется способ получить бинарь картинки с media-endpoint под JWT и отдать компоненту готовый objectURL.

**Изменения:**
- `shared/api/query-keys.ts` — новый ключ media-ресурса (напр. `queryKeys.projects.artifactMedia(projectId, artifactId)`),
  общий для карточки ленты и вьюера (react-query дедуплицирует один запрос на оба потребителя). Ключ — потомок
  `artifact(...)` в иерархии, чтобы префиксная инвалидация артефакта задевала и media.
- `shared/api/artifacts.ts`:
  - функция `getArtifactMedia(projectId, artifactId)` — `apiClient.get(.../media, { responseType: "blob" })`
    по образцу `downloadArtifact` (interceptor подставляет JWT). Возвращает `Blob` (и, при необходимости, mime из
    `response.headers["content-type"]` для расширения файла при скачивании).
  - хук `useArtifactMedia(projectId, artifactId)` — react-query по media-ключу: кэширует **Blob** (иммутабельный
    контент → `staleTime: Infinity` уместен), из него в потребителе делается `URL.createObjectURL` с revoke при
    размонтировании. Механику берём из design-brief § «Отдача на фронт»: react-query кэширует blob, objectURL
    освобождается на unmount. Хук `enabled` только при наличии обоих id.
  - `404` (блоб отсутствует) — не retry-ить как транзиентную ошибку; хук должен различать «нет блоба» и «сеть/500»,
    чтобы вьюер показал пустое состояние, а не крутилку (react-query `retry`: не повторять на 404).

**Verification:**
- `make check-fe` проходит (ESLint + Prettier + tsc).
- Функция бьёт по `GET /projects/{pid}/artifacts/{aid}/media` c `responseType: "blob"`; JWT приходит из
  существующего axios-interceptor (не дублируется руками).
- Ключ добавлен в фабрику `queryKeys` (инлайн-литералов ключей нет — конвенция frontend.md § «Фабрика query keys»).

### T2.2: Живой `ImageViewer` + раз-гейт ветки `image` в `ArtifactView`

**Цель:** страница артефакта показывает реальную картинку с состояниями загрузки/404, caption = prompt, скачиванием .png; ветка `image` выходит из-под dev-флага в прод.

**Изменения:**
- `pages/artifact/ui/ImageViewer.tsx`:
  - принимать `projectId` + `artifactId` (для `useArtifactMedia`) и `content` (prompt → caption под картинкой);
    `title`/`createdAt` остаются. Mock-дефолты из `mock-artifact-data` для image убрать (реальные данные приходят
    из `ArtifactView`); сам файл моков не трогаем — им ещё пользуются slides/audio.
  - подключить `useArtifactMedia`; тело картинки — `<img>` с objectURL, `alt` = prompt (`content`).
  - три состояния из мокапа (JS-логика мокапа = целевое поведение): **загрузка** — скелетон-шиммер на месте
    изображения (каркас header/зум/caption сохраняется); **готово** — картинка + зум-pill активен, кнопка «.png»
    включена; **404/нет блоба** — пустое состояние (иконка + mono-текст «изображение не найдено»), зум-pill скрыт,
    скачивание выключено. Существующий UI зума (`ZOOM_STEPS`, pill) сохраняется как есть.
  - кнопку «Открыть в окне» (`ExternalLink`) удалить (design-brief § Frontend).
  - кнопка «.png» скачивает **уже полученный blob** (не повторный запрос): `URL.createObjectURL(blob)` → anchor
    download; имя файла — из `title` (+ расширение по mime). Паттерн скачивания — как хвост `downloadArtifact`.
- `pages/artifact/ui/ArtifactView.tsx`:
  - ветку `image` вынести из-под `SHOW_GROUP_B_STUBS` (`if (type === "image") return <ImageViewer .../>`);
    slides/audio остаются гейтнутыми. Прокинуть в `ImageViewer` `projectId={id}`, `artifactId={aid}`,
    `title={data.title}`, `createdAt={formattedDate}`, `content={data.content}` (prompt из `ArtifactDetail`).

**Verification:**
- `make check-fe` проходит.
- Критерий приёмки: `ImageViewer` показывает реальную картинку (fetch с JWT → objectURL), состояния
  загрузки/404, caption = prompt, скачивание .png; ветка `image` выведена из-под `SHOW_GROUP_B_STUBS`.
- Кнопки «Открыть в окне» в вьюере нет; зум-pill скрыт в состоянии 404, «.png» задизейблена вне «готово».
- Хардкода цветов/hex в `.tsx` нет — только токены/Tailwind (frontend.md § «Дизайн-токены»).

### T2.3: Превью image-артефакта в карточке ленты `ArtifactCard`

**Цель:** карточка артефакта `type === "image"` показывает миниатюру 64×40 (то же изображение с media-endpoint) вместо типовой иконки; прочие типы — как раньше.

**Изменения:**
- `pages/chat/ui/ArtifactCard.tsx`:
  - для `type === "image"` — на месте иконки `FileText` миниатюра 64×40 (`w-16 h-14`≈ по мокапу `4rem × 2.5rem`,
    скруглённая, с бордером, `object-fit: cover`), источник — `useArtifactMedia(projectId, artifact.id)` (тот же
    media-ключ → react-query дедуплицирует запрос со вьюером, immutable-кэш браузера снимает повторные загрузки).
  - на время загрузки миниатюры — шиммер в зоне превью; при ошибке/404 — грациозный фолбэк на иконку (не битый
    `<img>`), консистентно с 404-состоянием вьюера. Остальная вёрстка карточки (`ArtifactCard`) не меняется.
  - не-image типы — прежняя ветка с `FileText`. `projectId` в карточку уже приходит.
- Карточка используется и в `MessageList` (стрим), и в `MessageItem` (персистентная лента) — правка одна, покрывает
  оба пути; отдельных изменений в этих файлах не требуется.

**Verification:**
- `make check-fe` проходит.
- Критерий приёмки: карточка image-артефакта в ленте с превью (то же изображение с media-endpoint).
- Не-image карточки визуально не изменились; миниатюра только для `type === "image"`.

### T2.4: Плейсхолдер на время генерации (`tool_start`/`tool_end` по `call_id`)

**Цель:** по началу генерации в ленту встаёт pending-карточка (шиммер-миниатюра, «Генерирую изображение…»,
indeterminate прогресс-бар), которая снимается по завершению tool'а; реальная карточка приходит по `artifact_created`.

**Изменения (целиком фронтовая логика на существующих SSE-событиях — протокол и бэкенд не меняются):**
- `stores/stream-store.ts` — новое состояние для отслеживания активных генераций изображений по `call_id`
  (напр. `pendingImages: string[]` + `addPendingImage(callId)` / `removePendingImage(callId)`), сбрасывается в
  `startStream`/`endStream` вместе с прочим стрим-состоянием. Существующий `activeTool` (для `ToolIndicator`) не ломаем.
- `pages/chat/model/useAgentStream.ts`:
  - `tool_start` c `tool === "generate_image"` → `addPendingImage(event.call_id)` (в дополнение к текущему
    `setTool`); прочие tool'ы — без изменений.
  - `tool_end` c тем же `call_id` → `removePendingImage(event.call_id)`. Приходит и при ошибке tool'а —
    плейсхолдер не зависает (design-brief § Frontend). `call_id` сейчас в switch не читается — начать читать.
- `pages/chat/ui/MessageList.tsx` — в блоке `isStreaming` отрисовать по одной pending-карточке на каждый активный
  `call_id` (подписка на новое поле стора через селектор). Вёрстка плейсхолдера — из мокапа: та же карточка,
  зона миниатюры — шиммер, заголовок «Генерирую изображение…» (title не показываем — `tool_start` аргументов не
  несёт), indeterminate progress-bar. Реализовать как небольшой презентационный компонент (напр.
  `GeneratingArtifactCard` в `pages/chat/ui/`) либо placeholder-ветку карточки — на усмотрение implementer'а;
  реальные карточки по-прежнему приходят через `streamingArtifacts` (`artifact_created`).

**Verification:**
- `make check-fe` проходит.
- Критерий приёмки: плейсхолдер на время генерации по `tool_start`/`tool_end` (только фронт, протокол не меняется).
- Плейсхолдер появляется по `tool_start(generate_image)`, снимается по `tool_end` с тем же `call_id` (в т.ч. при
  ошибке tool'а — не зависает); реальная карточка встаёт по `artifact_created`.
- Существующее поведение `ToolIndicator`/`activeTool` для прочих tool'ов не изменилось (регресс отсутствует).

## Cross-cutting

Проверить после всех фаз трека:

- `make check-fe` зелёный на итоговом состоянии трека.
- Все критерии приёмки feat-010, относящиеся к фронту (tasklist § «Критерии приёмки»):
  живой `ImageViewer` (fetch+JWT, состояния, caption=prompt, .png), карточка с превью, плейсхолдер генерации,
  ветка `image` вне `SHOW_GROUP_B_STUBS`.
- Общий media-ключ реально дедуплицирует запрос карточки и вьюера (один сетевой вызов на пару потребителей).
- objectURL освобождается при размонтировании потребителей (нет утечки), Blob остаётся в react-query кэше.
- Stub-gating не нарушен: slides/audio остаются под `SHOW_GROUP_B_STUBS`; раз-гейтнут только `image`.
- Токены/темизация: светлая и тёмная тема корректны (мокап проверялся на обеих) — визуальная сверка с мокапом.
- Colocated Vitest-тесты по треку пишет `test-author` отдельно — здесь не предписываются.

## Open Questions

Нет открытых вопросов. Разрешено архитектором на эскалации оркестратора (до старта
реализации):

1. **`ToolIndicator` vs плейсхолдер-карточка** → пилюлю `ToolIndicator` для
   `tool === "generate_image"` **подавлять** (pending-карточка её замещает, по мокапу);
   для прочих tools поведение пилюли не меняется. Учесть в условии рендера `activeTool`
   в `MessageList` (фаза T2.4).
