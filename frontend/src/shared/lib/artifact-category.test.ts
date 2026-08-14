import { describe, expect, it } from "vitest";

import { getArtifactCategory } from "./artifact-category";

// Unit: словарь «расширение → категория вьюера» (feat-011, T2.2). Единственный
// источник категории для трёх слайсов — вьюер, список артефактов и карточка
// чата, — поэтому проверяется он сам, а не каждый потребитель по отдельности.
// Контракт из design-brief § Артефакты: `md` — markdown, растровые расширения —
// image, нераспознанное расширение с содержимым — обычный текст, без
// содержимого — бинарный файл (метаданные + скачивание).

describe("getArtifactCategory", () => {
  it("markdown-расширение открывается markdown-вьюером", () => {
    expect(getArtifactCategory("md")).toBe("markdown");
  });

  it.each(["png", "jpg", "jpeg", "webp", "gif"])(
    "растровое расширение %s открывается image-вьюером",
    (type) => {
      expect(getArtifactCategory(type)).toBe("image");
    },
  );

  it.each(["txt", "csv", "py", "json", "yaml"])(
    "нераспознанное расширение %s с содержимым читается как текст",
    (type) => {
      // Штатный выход `write_file`/джобы: файл, у которого detail отдал
      // `content`, показывается моно-рендером, а не заглушкой «недоступно».
      expect(getArtifactCategory(type, true)).toBe("text");
    },
  );

  it.each(["pdf", "docx", "xlsx", "zip"])(
    "нераспознанное расширение %s без содержимого читается как бинарник",
    (type) => {
      expect(getArtifactCategory(type, false)).toBe("binary");
    },
  );

  it("изображение остаётся изображением и без content в detail", () => {
    // Detail бинарного файла `content` не отдаёт вовсе (design-brief
    // § Артефакты), а тело картинки приезжает с media-эндпоинта: если бы
    // отсутствие `content` перебивало расширение, png открывался бы
    // заглушкой «Предпросмотр недоступен» вместо картинки.
    expect(getArtifactCategory("png", false)).toBe("image");
    expect(getArtifactCategory("md", false)).toBe("markdown");
  });

  it("расширение в верхнем регистре не меняет категорию", () => {
    expect(getArtifactCategory("PNG")).toBe("image");
    expect(getArtifactCategory("MD")).toBe("markdown");
  });

  it("без знания о content расширение считается текстовым, а не бинарным", () => {
    // Список и карточка чата detail не грузят и о наличии `content` не знают:
    // там рисуется только иконка/подпись, поэтому дефолт оптимистичный.
    expect(getArtifactCategory("txt")).toBe("text");
  });
});
