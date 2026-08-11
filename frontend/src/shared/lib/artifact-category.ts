/**
 * Словарь «расширение → категория вьюера/иконки» для файловой модели
 * артефактов (ADR-032). `Artifact.type`/`ArtifactDetail.type` — это
 * расширение файла без точки ("md", "png", …), не семантическая метка:
 * раньше фронт ветвился по `type === "image"`, теперь категорию выводит
 * этот словарь.
 *
 * Общий модуль для трёх слайсов-потребителей — вьюер (`pages/artifact`),
 * список (`pages/artifacts`), карточка в чате (`pages/chat`). Ни один из
 * них не является родителем другого, а размещение в `pages/artifact`
 * означало бы запрещённый FSD-кросс-импорт pages→pages — поэтому словарь
 * стоит в `shared/lib`.
 */

export type ArtifactCategory = "markdown" | "image" | "text" | "binary";

const IMAGE_EXTENSIONS: ReadonlySet<string> = new Set([
  "png",
  "jpg",
  "jpeg",
  "webp",
  "gif",
]);

/**
 * @param type - расширение артефакта (`Artifact.type`), без точки.
 * @param hasContent - есть ли у detail поле `content` (у бинарного файла его
 *   нет). Различает нераспознанное расширение с текстовым телом — обычный
 *   текстовый файл (`.txt`, `.csv`, `.py`, `.json`, … — штатный выход
 *   `write_file`/джобы) — от бинарного файла без него. Список/карточка не
 *   всегда грузят detail и не знают присутствие `content` заранее — по
 *   умолчанию `true` (оптимистично «текст»): там рендерится только
 *   иконка/подпись, а не тело файла, поэтому редкая ошибка категории на
 *   бинарнике без detail не бьёт по функциональности.
 */
export function getArtifactCategory(
  type: string,
  hasContent = true,
): ArtifactCategory {
  const ext = type.toLowerCase();
  if (ext === "md") return "markdown";
  if (IMAGE_EXTENSIONS.has(ext)) return "image";
  return hasContent ? "text" : "binary";
}
