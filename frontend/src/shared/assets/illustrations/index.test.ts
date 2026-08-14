import { describe, expect, it } from "vitest";

import { getIllustration, type IllustrationTheme, type Scene } from "./index";

// Unit (чистая функция): карта иллюстраций — единственная точка свапа ассетов.
// Страхуем от полупустой карты: сцена, заведённая в тип, но забытая в одной из
// тем, ломает экран только в рантайме и только в одной теме.

// Ключи перечислены объектом `Record<Scene, true>`, а не массивом: пропуск сцены
// падает на `tsc` (`make check-fe`), поэтому список не разъедется с типом.
// Полноту карты сторожит именно этот тип, а не рантайм-ассерт на длину: такой
// ассерт мерил бы литерал самого теста, прод-код в нём не участвует.
const ALL_SCENES: Record<Scene, true> = {
  "welcome-hero": true,
  "sidebar-vignette": true,
  "empty-chats": true,
  "empty-sphere": true,
  "empty-artifacts": true,
  "error-state": true,
  "not-found": true,
  "artifacts-select": true,
  "auth-hero": true,
};

const scenes = Object.keys(ALL_SCENES) as Scene[];
const themes: IllustrationTheme[] = ["light", "dark"];

const pairs = scenes.flatMap((scene) =>
  themes.map((theme): [Scene, IllustrationTheme] => [scene, theme]),
);

describe("getIllustration", () => {
  // Ассерт на путь целиком, а не на расширение: самый вероятный дефект карты —
  // копипаста в одной из 18 почти одинаковых строк (`dark: { "not-found":
  // artifactsSelectDark }`). Проверка `.png` на такую подмену слепа, проверка
  // `/<theme>/<scene>.png` — нет: она разом закрывает «это PNG», «это та тема»
  // и «это та сцена».
  it.each(pairs)("отдаёт ассет сцены %s из темы %s", (scene, theme) => {
    expect(getIllustration(scene, theme)).toMatch(
      new RegExp(`/${theme}/${scene}\\.png$`),
    );
  });

  it.each(scenes)("разводит темы для сцены %s", (scene) => {
    expect(getIllustration(scene, "light")).not.toBe(
      getIllustration(scene, "dark"),
    );
  });
});
