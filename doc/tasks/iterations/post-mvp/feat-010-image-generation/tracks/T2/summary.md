# Post-implementation summary: feat-010 / трек T2

## Фаза T2.1: Media-фетч и хук `useArtifactMedia`

Добавлен способ получить бинарь image-артефакта с media-endpoint под JWT и отдать
потребителю (карточке ленты, вьюеру — следующие фазы) готовый `Blob` из кэша react-query.

`frontend/src/shared/api/query-keys.ts`:
- новый ключ `queryKeys.projects.artifactMedia(id, artifactId)` — потомок
  `queryKeys.projects.artifact(...)` в иерархии (`[...artifact(id, artifactId), "media"]`),
  так что префиксная инвалидация артефакта (`invalidateQueries({ queryKey: artifact(id, artifactId) })`)
  задевает и media-запись.

`frontend/src/shared/api/artifacts.ts`:
- `getArtifactMedia(projectId, artifactId)` — `apiClient.get(.../media, { responseType: "blob" })`,
  по образцу `downloadArtifact`; JWT подставляет существующий axios-interceptor, руками не
  дублируется. Возвращает `Blob`.
- `useArtifactMedia(projectId, artifactId)` — react-query хук по новому ключу; `enabled`
  только при наличии обоих id; `staleTime: Infinity` (иммутабельный контент — перегенерация
  создаёт новый артефакт/id, значит и новый URL).
- `isArtifactMediaNotFound(error)` — типизированный предикат (`AxiosError` + `status === 404`),
  по образцу `isSecurityViolation` из `shared/lib/security-error.ts`. Экспортирован для
  потребителей следующих фаз (T2.2 `ImageViewer`, T2.3 `ArtifactCard`), которым нужно отличить
  «блоба нет» от сетевой/500-ошибки, чтобы показать пустое состояние, а не крутилку/тост.

**Verification:** `make check-fe` — зелёный (tsc -b --noEmit, eslint, prettier --check).

## Фаза T2.2: Живой `ImageViewer` + раз-гейт ветки `image` в `ArtifactView`

Страница артефакта показывает реальную картинку вместо визуальной заглушки; ветка
`type === "image"` в `ArtifactView` выведена из-под `SHOW_GROUP_B_STUBS` в прод (slides/audio
остаются под флагом — не тронуты).

`frontend/src/pages/artifact/ui/ImageViewer.tsx`:
- принимает `projectId`/`artifactId` (для `useArtifactMedia`) и `content` (prompt → caption и
  `alt`); mock-дефолты (`MOCK_IMAGE_TITLE`/`MOCK_IMAGE_CREATED_AT`/`MOCK_IMAGE_CAPTION`) убраны из
  компонента — реальные данные приходят из `ArtifactView`. Файл `mock-artifact-data.ts` не
  тронут (slides/audio продолжают им пользоваться).
- `useArtifactMedia(projectId, artifactId)` отдаёt `Blob`; из него `useEffect` создаёт
  `URL.createObjectURL`, ревокается при смене/размонтировании (cleanup-функция эффекта). Явного
  состояния «загрузка» из хука (`isLoading`) в JSX не читается: три визуальных состояния выводятся
  из `objectUrl`/`isError` (см. ниже), поэтому лишнее поле сломало бы `noUnusedLocals` (`tsc -b`) —
  проверено на прогоне `make check-fe`, отдельно объяснено в «Решениях».
- три состояния (JS-логика мокапа `image-artifacts.html` — целевое поведение):
  **загрузка** — `objectUrl === null && !isError` → шиммер (`animate-pulse bg-muted`) на месте
  картинки, каркас (header/зум-pill/caption) на месте; **готово** — `objectUrl` есть → `<img>`
  на весь бокс (`object-cover`), зум-pill активен, кнопка «.png» включена; **404/нет блоба** —
  `isError && !objectUrl` → пустое состояние (`ImageOff` + mono-текст), зум-pill скрыт (условный
  рендер), «.png» задизейблена.
- кнопка «Открыть в окне» (`ExternalLink`) удалена вместе с импортом.
- кнопка «.png» скачивает уже полученный `blob`/`objectUrl` (без повторного запроса): создаёт
  `<a>` с `href={objectUrl}`, `download` — `${title}.${ext}`, `ext` — из `blob.type` (второй
  сегмент MIME, `"image/png"` → `"png"`). Паттерн — хвост `downloadArtifact` (создать `<a>`,
  `click()`, убрать из DOM), без `URL.revokeObjectURL` сразу после клика — `objectUrl` тот же,
  что рендерит `<img>`, ревокается общим cleanup-эффектом, а не в обработчике скачивания.
- существующий UI зума (`ZOOM_STEPS`, pill, `cn`) не менялся — только контент бокса переключается
  по состоянию; бокс сохранил фиксированный `aspectRatio: "4 / 3"` во всех трёх состояниях (было
  так и до фазы) — единая рамка независимо от реальных пропорций картинки (16:9/1:1/21:9 по
  design-brief), `object-cover` внутри кадрирует.

`frontend/src/pages/artifact/ui/ArtifactView.tsx`:
- ветка `image` вынесена из-под `SHOW_GROUP_B_STUBS` (`if (type === "image") return <ImageViewer .../>`,
  без флага); slides/audio остались как были, под флагом. Комментарий над type-dispatch обновлён:
  зафиксировано, что `image` (feat-010, трек T1) — реальный бэкенд-контракт, а не mock-заглушка,
  в отличие от slides/audio.
- в `ImageViewer` прокинуты `projectId={id}`, `artifactId={aid}`, `title={data?.title}`,
  `createdAt={formattedDate}`, `content={data?.content}` (`content` — prompt из `ArtifactDetail`).

**Verification:** `make check-fe` — зелёный (tsc -b --noEmit, eslint, prettier --check).

## Фаза T2.3: Превью image-артефакта в карточке ленты `ArtifactCard`

Карточка артефакта `type === "image"` показывает миниатюру 64×40 (то же изображение
с media-endpoint) вместо типовой иконки `FileText`; прочие типы не изменились.

`frontend/src/pages/chat/ui/ArtifactCard.tsx`:
- ветвление по `artifact.type === "image"`: image-артефакты рендерят новый локальный
  компонент `ArtifactThumbnail`, прочие типы — прежний `FileText`. Остальная вёрстка
  карточки (`Link`, `borderLeft`, title/type) не тронута — один компонент покрывает оба
  места использования (`MessageList` — стрим, `MessageItem` — персистентная лента), в
  этих файлах правок не потребовалось (карточка получает `artifact`/`projectId`, как и
  раньше).
- `ArtifactThumbnail(projectId, artifactId)` — `useArtifactMedia(projectId, artifactId)`
  по тому же media-ключу, что и `ImageViewer` (T2.2): react-query дедуплицирует сеть
  между карточкой в ленте и вьюером — если пользователь уже открывал артефакт (или
  наоборот, открывает после того как карточка отрендерилась), второго HTTP-запроса не
  происходит, оба потребителя читают один закэшированный `Blob`.
- `objectUrl` из `blob` — тот же паттерн, что в `ImageViewer.tsx` (T2.2): локальный
  `useState` + `useEffect` с `URL.createObjectURL`/`revokeObjectURL` в cleanup, не
  `useMemo` (создание objectURL — побочный эффект, не должен жить в теле рендера).
  Сознательное дублирование ~10 строк между `ArtifactCard.tsx` и `ImageViewer.tsx`, а не
  общий хук уровня `shared/` — вне скоупа фазы (план T2.3 не предписывал такое
  выделение, а это уже архитектурное решение по обобщению; каждый потребитель к тому же
  использует только часть состояний: карточка не читает `error` для различения
  404/сеть, вьюер — читает).
- три визуальных состояния зоны превью (64×40, `rounded-sm`, `border-border`, box
  сохраняется одного размера во всех состояниях — консистентно с мокапом
  `image-artifacts.html` § `.artifact-card .thumb`):
  **загрузка** — `!objectUrl && !isError` → `animate-pulse bg-muted` (тот же токен
  шиммера, что `ImageViewer`); **готово** — `objectUrl` есть → `<img object-cover>` на
  весь бокс; **ошибка/404** — `isError` → `bg-muted` + иконка `ImageOff` по центру
  (`h-4 w-4`, приглушённая непрозрачность), без битого `<img src>` — тот же принцип
  «явный фолбэк, не сломанная картинка», что в пустом состоянии `ImageViewer`. Отдельно
  текст 404 vs сетевая ошибка (как в `ImageViewer` через `isArtifactMediaNotFound`) в
  карточке не выводится — в 64×40 нет места под текст, разница ошибок не несёт
  пользовательской ценности на этом масштабе; card остаётся кликабельной (переход в
  `ImageViewer`, который уже различает 404/сеть текстом), поэтому потеря нюанса не
  критична.
- `<img alt="">` и `aria-hidden="true"` на контейнере превью — миниатюра декоративна
  (та же информация — title/type — уже озвучена соседним текстовым блоком карточки),
  консистентно с мокапом (`aria-hidden="true"` на `.thumb` в обоих состояниях карточки).
- размер `h-10 w-16` (2.5rem × 4rem = 40×64px) — по CSS мокапа
  (`.artifact-card .thumb { width: 4rem; height: 2.5rem; }`), не по буквальному тексту
  плана («`w-16 h-14`≈ по мокапу `4rem × 2.5rem`» — `h-14` в Tailwind это 3.5rem, что
  противоречит указанным тут же `2.5rem`; взял мокап как источник истины, поскольку план
  явно ссылается на него как на образец, а числовое несовпадение — техническая опечатка
  в тексте плана, не отдельное решение).
- скругление `rounded-sm` (`--radius-sm` = `calc(var(--radius) * 0.6)` = 0.42rem) —
  ближайший токен к `0.35rem` мокапа; точного токена под это значение в палитре нет,
  `rounded-sm` уже используется в проекте для мелких декоративных элементов
  (`SphereVersionPanel.tsx`, `SphereWriteCard.tsx`) — тот же класс масштаба, что
  миниатюра карточки.

**Verification:** `make check-fe` — зелёный (tsc -b --noEmit, eslint, prettier --check).

## Фаза T2.4: Плейсхолдер на время генерации (`tool_start`/`tool_end` по `call_id`)

По началу генерации в ленту встаёт pending-карточка (шиммер-миниатюра, «Генерирую
изображение…», indeterminate прогресс-бар), которая снимается по завершению tool'а
(в т.ч. при ошибке); реальная карточка приходит по `artifact_created` как раньше.
Протокол SSE и бэкенд не менялись — логика целиком фронтовая, поверх уже существующих
событий.

`frontend/src/stores/stream-store.ts`:
- новое поле `pendingImages: string[]` — call_id активных генераций изображений;
  экшены `addPendingImage(callId)` (идемпотентный — не дублирует id, если по какой-то
  причине `tool_start` придёт дважды с тем же `call_id`) и `removePendingImage(callId)`
  (`filter`, no-op если id уже отсутствует — покрывает и штатное снятие, и потенциальный
  повторный `tool_end`). Сброс в `startStream`/`endStream` вместе с прочим
  стрим-состоянием — симметрично `streamingArtifacts`. `activeTool` не тронут.

`frontend/src/pages/chat/model/useAgentStream.ts`:
- `event.call_id` теперь читается в `switch` (раньше игнорировался): `tool_start` c
  `tool === "generate_image"` → `addPendingImage(event.call_id)` в дополнение к
  существующему `setTool(event.tool)`; `tool_end` с тем же условием →
  `removePendingImage(event.call_id)` в дополнение к `setTool(null)`. `tool_end`
  приходит и при ошибке tool'а (сервер эмитит его в `finally`-эквиваленте на бэкенде,
  вне зависимости от исхода) — плейсхолдер не зависает. Прочие tool'ы — ветки не
  затронуты.

`frontend/src/pages/chat/ui/GeneratingArtifactCard.tsx` (новый файл):
- презентационный компонент без пропсов — рендерится по одному на активный `call_id`.
  Вёрстка — та же карточка, что `ArtifactCard` (тот же `rounded-md bg-card p-3` +
  `borderLeft: 3px solid var(--ring)`, тот же размер миниатюры `h-10 w-16
  rounded-sm border-border`), но статична (`div`, не `Link` — клик никуда не ведёт,
  артефакта ещё нет), `role="status" aria-label="Идёт генерация изображения"` — по
  мокапу (`image-artifacts.html` `#genCardRow`, `role="status"`).
- title всегда «Генерирую изображение…» — `tool_start` не несёт аргументов (prompt
  недоступен на этой стадии), план прямо фиксирует «title не показываем».
- indeterminate прогресс-бар — новый CSS-keyframe `gen-progress-indeterminate` в
  `frontend/src/index.css` (аналога бегущей полосы в `tw-animate-css` нет; шиммер
  миниатюры переиспользует существующий `animate-pulse`). `@media
  (prefers-reduced-motion: reduce)` — анимация выключается, полоса статично залита
  (`opacity: 0.35; width: 100%`), тот же паттерн, что `.genbar-run` в мокапе.

`frontend/src/pages/chat/ui/MessageList.tsx`:
- подписка на `pendingImages` через селектор Zustand (`useStreamStore((s) =>
  s.pendingImages)`) — по тому же паттерну, что уже применён к `isReviewing` в этом
  файле; рендер `pendingImages.map((callId) => <GeneratingArtifactCard key={callId}
  />)` в блоке `isStreaming`, перед `streamingArtifacts` (реальные карточки логически
  идут после плейсхолдеров, если несколько генераций сериализованы).
- `ToolIndicator` подавлена для `tool === "generate_image"` (решение архитектора,
  Open Questions плана): условие рендера изменено с `activeTool &&
  <ToolIndicator .../>` на `activeTool && activeTool !== "generate_image" &&
  <ToolIndicator .../>`. Для прочих tool'ов пилюля рендерится как раньше — регресса
  нет (проверено чтением: единственная точка рендера `ToolIndicator` в файле, других
  мест использования компонента в кодовой базе нет).

**Verification:** `make check-fe` — зелёный (tsc -b --noEmit, eslint, prettier --check).

## Решения и обоснования

**Ретраи на 404 — не переопределялись в хуке.** План требовал «хук должен различать «нет
блоба» и «сеть/500», … react-query `retry`: не повторять на 404». Проверил
`frontend/src/app/providers/QueryProvider.tsx:19-25` (`shouldRetryQuery`): глобальный дефолт
`QueryClient` уже не ретраит весь диапазон `4xx` (включая 404) и ограниченно ретраит 5xx/сеть
(`failureCount < 2`, синхронизировано с backend `max_retries=2`, D-ERR-9). Добавлять в
`useArtifactMedia` собственный `retry` было бы дублированием уже верной глобальной политики —
рассмотрено и отклонено. Вместо этого добавлен `isArtifactMediaNotFound` — тонкий слой
классификации ошибки поверх уже правильного поведения ретраев, а не замена ему.

**Mime не извлекается из заголовка отдельно.** План допускал доставание mime из
`response.headers["content-type"]` «при необходимости» — для формирования расширения файла при
скачивании (кнопка «.png» в T2.2). Проверено: при `responseType: "blob"` браузер (XHR/fetch-адаптер
axios) сам конструирует `Blob` с `.type`, выставленным из `Content-Type` ответа — значит
`blob.type` уже несёт mime без отдельного чтения заголовка. Возвращать из `getArtifactMedia`
кортеж `{ blob, mimeType }` вместо голого `Blob` рассмотрено и отклонено: `Blob.type` — тот же
источник данных, вторая копия только добавляла бы риск рассинхронизации и лишний тип в публичном
API функции. Потребитель T2.2 при необходимости читает `blob.type` напрямую.

**`isArtifactMediaNotFound` вынесен как экспортируемый хелпер в `artifacts.ts`, а не в
`shared/lib/`.** Логика узкоспециализирована под media-эндпоинт артефактов (не общий
паттерн уровня приложения, как `getApiErrorMessage`), поэтому колоцирована рядом с
`getArtifactMedia`/`useArtifactMedia` — тем самым потребителю в `pages/artifact` и
`pages/chat` (T2.2/T2.3) нужен один импорт из `shared/api/artifacts`, а не два модуля.
Паттерн подсмотрен у `isSecurityViolation` (`shared/lib/security-error.ts`) — тот же приём
«типизированный предикат по `AxiosError.response.status`», но применённый локально к своему
домену, а не как общий lib-хелпер, потому что 404 «блоба нет» — семантика конкретно
media-ресурса, не общая для всех API вызовов проекта.

**Функция `getArtifactMedia` без явного дефолтного значения формата/типа** (в отличие от
`downloadArtifact`, где есть `format: "md" | "pdf" = "md"`) — у media-endpoint нет вариативности
формата на входе (bytes как есть, `Content-Type` определяет сервер по `mime_type` артефакта),
поэтому сигнатура ограничена `projectId`/`artifactId`, лишних параметров не введено.

**T2.2: пустое состояние — единое на `isError`, без ветвления по типу ошибки в вёрстке.** Design-brief
и мокап описывают ровно два нефинальных состояния сверх «готово» — «загрузка» и «404 без блоба».
Реализация не разводит в UI 404 и сетевую/500-ошибку после исчерпания ретраев (`shouldRetryQuery` в
`QueryProvider.tsx` не ретраит 4xx и ограниченно ретраит 5xx/сеть — оба класса ошибок в итоге дают
`isError === true`): читатель получает то же пустое состояние (иконка + mono-текст), а не крутилку —
именно это и было целью классификации в T2.1. Единственная уступка различию — текст под иконкой
берёт `isArtifactMediaNotFound` для более точной формулировки («изображение не найдено» при 404 vs
«не удалось загрузить изображение» при прочих ошибках), сама вёрстка/расположение элементов —
идентичны. Введение отдельного третьего визуального состояния (network-error, отличного от 404)
рассмотрено и отклонено — вне мокапа и design-brief, архитектурное решение вне скоупа фазы.

**T2.2: бокс изображения сохраняет фиксированный `aspectRatio: "4 / 3"` во всех трёх состояниях**,
а не адаптируется под естественные пропорции загруженной картинки (16:9/1:1/21:9 — design-brief
§ «Промптинг»). Мокап `image-artifacts.html` использует свой фиксированный `16 / 9` только для
демо-SVG — сам факт «единая рамка + `object-fit: cover`» является целевым паттерном (кадрирование,
не подгонка бокса под контент), а не конкретное числовое значение. `4 / 3` — значение,
унаследованное от прежней заглушки (правка минимальна, без несанкционированного визуального
решения); смена соотношения — вопрос дизайна, не затронутый планом фазы, эскалация не требовалась,
т.к. `object-fit: cover` одинаково маскирует расхождение вне зависимости от выбранного числа.

**T2.2: `objectUrl` — отдельный `useState`, обновляемый в `useEffect`, а не `useMemo` на `blob`.**
Создание `URL.createObjectURL` в теле рендера (через `useMemo`) — побочный эффект вне
`useEffect`/обработчика, что при `StrictMode`/двойном рендере в dev создаёт лишние objectURL без
детерминированного момента ревокации существующего. `useEffect` с cleanup — стандартный React-паттерн
для ресурсов с ручным освобождением; цена — один лишний рендер-кадр между приходом `blob` и
готовностью `objectUrl` (в это время видна та же шиммер-заглушка, что и во время самого fetch,
поэтому пользователь не видит разницы).

**T2.2: `isLoading` из `useArtifactMedia` не используется явно в `ImageViewer`.** Состояние
«загрузка» выведено как единственный оставшийся вариант (`!objectUrl && !isError`), а не через
`isLoading` из хука — иначе пришлось бы держать в уме два независимых источника правды
(`isLoading` от react-query и `objectUrl` от локального эффекта) для одного и того же визуального
состояния, с риском рассинхронизации кадра между «`isLoading` стал false» и «`objectUrl` ещё не
создан». Деструктурировать `isLoading` без использования не стал — `tsc -b --noEmit` (`noUnusedLocals`)
не пропустил бы.

## Follow-ups

## SOFA-посты (id / применил / результат)
