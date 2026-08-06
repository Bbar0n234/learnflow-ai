/**
 * Фиче-флаги фронтенда.
 *
 * `SHOW_GROUP_B_STUBS` — незрелые фичи группы B: версионирование Сферы,
 * SSE-peek карточка записи в Сферу, studio-панель и линза, просмотрщики
 * slides/audio. Реализованы на фронтенд-заглушках (mock-данные) — бэкенд-
 * контракта под них пока нет (см. doc/backlog.md, секция Backend).
 *
 * Opt-in только для dev: по умолчанию выключен везде, включается для
 * локального догфудинга дизайна через `VITE_SHOW_GROUP_B_STUBS=true`
 * (в `frontend/.env.local` или инлайн при запуске `make dev-fe`). В любой
 * собранной/задеплоенной сборке (`vite build`, MODE=production) `DEV`
 * статически равен `false`, ветки не рендерятся, а мок-данные выпадают из
 * бандла через dead-code elimination. Прод-пользователь фейковых данных
 * не видит независимо от переменной.
 *
 * Снимать по мере появления реального бэкенда: когда у фичи группы B есть
 * контракт, её код раз-гейтится индивидуально в месте рендера (так уже
 * раз-гейчен image-viewer — живёт на реальном media endpoint без флага).
 */
export const SHOW_GROUP_B_STUBS =
  import.meta.env.DEV && import.meta.env.VITE_SHOW_GROUP_B_STUBS === "true";

/**
 * SIEM kill-switch: включает роут `/security` и кнопку «Безопасность» в сайдбаре.
 *
 * Build-time флаг — значение вшивается в бандл на этапе сборки (`vite build`),
 * смена требует пересборки, а не рестарта процесса. В docker-сборке значение
 * приезжает из бэкендового `SIEM_ENABLED` через `build.args` в docker-compose.
 *
 * Семантика «всё, что не литеральное `"false"`, означает включено» — дефолт
 * `true`: сборка без build-args (`make dev-fe`, голый `npm run build`, `vite dev`)
 * ведёт себя как сейчас.
 *
 * В отличие от `SHOW_GROUP_B_STUBS`, флаг не привязан к `import.meta.env.DEV` —
 * он обязан быть выставляемым именно в прод-сборке.
 */
export const SIEM_ENABLED =
  (import.meta.env.VITE_SIEM_ENABLED ?? "true") !== "false";
