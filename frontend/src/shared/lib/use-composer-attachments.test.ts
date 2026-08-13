import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  formatFileSize,
  useComposerAttachments,
} from "./use-composer-attachments";

// Unit: клиентское состояние вложений композера (feat-011, T2.8). До отправки
// сообщения файл живёт только в браузере (design-brief § Тайминг) — этот хук и
// есть то место, где он живёт: добавление, независимое снятие чипа и сброс
// после успешной отправки.

function file(name: string, size = 10): File {
  const blob = new File(["x".repeat(size)], name, { type: "text/plain" });
  return blob;
}

describe("useComposerAttachments", () => {
  it("держит прикреплённые файлы в порядке выбора", () => {
    const { result } = renderHook(() => useComposerAttachments());

    act(() => result.current.addFiles([file("notes.md"), file("data.csv")]));

    expect(result.current.attachments.map((a) => a.file.name)).toEqual([
      "notes.md",
      "data.csv",
    ]);
  });

  it("дописывает файлы второго выбора к уже прикреплённым", () => {
    const { result } = renderHook(() => useComposerAttachments());

    act(() => result.current.addFiles([file("notes.md")]));
    act(() => result.current.addFiles([file("slides.pdf")]));

    expect(result.current.attachments.map((a) => a.file.name)).toEqual([
      "notes.md",
      "slides.pdf",
    ]);
  });

  it("снимает ровно тот чип, который убрали", () => {
    const { result } = renderHook(() => useComposerAttachments());
    act(() => result.current.addFiles([file("notes.md"), file("data.csv")]));

    const target = result.current.attachments[1]!;
    act(() => result.current.removeAttachment(target.id));

    expect(result.current.attachments.map((a) => a.file.name)).toEqual([
      "notes.md",
    ]);
  });

  it("два одноимённых файла убираются независимо", () => {
    // Идентичность чипа — не имя файла: два `notes.md` из разных папок
    // прикрепляются оба, и ✕ на одном не должна уносить второй.
    const { result } = renderHook(() => useComposerAttachments());
    act(() => result.current.addFiles([file("notes.md"), file("notes.md")]));

    expect(result.current.attachments).toHaveLength(2);
    act(() =>
      result.current.removeAttachment(result.current.attachments[0]!.id),
    );

    expect(result.current.attachments).toHaveLength(1);
    expect(result.current.attachments[0]!.file.name).toBe("notes.md");
  });

  it("сброс после отправки очищает композер целиком", () => {
    const { result } = renderHook(() => useComposerAttachments());
    act(() => result.current.addFiles([file("notes.md"), file("data.csv")]));

    act(() => result.current.clear());

    expect(result.current.attachments).toEqual([]);
  });

  it("пустой выбор файлов ничего не добавляет", () => {
    // Отмена системного диалога даёт пустой `FileList` — она не должна
    // порождать ни чипа, ни перерисовки состояния.
    const { result } = renderHook(() => useComposerAttachments());
    act(() => result.current.addFiles([file("notes.md")]));
    const before = result.current.attachments;

    act(() => result.current.addFiles([]));

    expect(result.current.attachments).toBe(before);
  });
});

describe("formatFileSize", () => {
  it.each([
    { bytes: 0, expected: "0 Б" },
    { bytes: 512, expected: "512 Б" },
    { bytes: 1023, expected: "1023 Б" },
    { bytes: 1024, expected: "1 КБ" },
    { bytes: 1024 * 512, expected: "512 КБ" },
    { bytes: 1024 * 1024, expected: "1,0 МБ" },
    { bytes: 1024 * 1024 * 2.5, expected: "2,5 МБ" },
  ])("$bytes байт читается как «$expected»", ({ bytes, expected }) => {
    expect(formatFileSize(bytes)).toBe(expected);
  });
});
