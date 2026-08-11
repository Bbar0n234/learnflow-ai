import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { attachFiles as attach } from "@/test/file-input";
import { renderWithProviders } from "@/test/test-utils";

import { ChatInput } from "./ChatInput";

// Integration: композер существующего чата со вложениями (feat-011, T2.8).
// Проверяется тайминг из design-brief § Вложения пользователя глазами
// композера: до отправки файл живёт только в состоянии `ChatInput` (сетевого
// пути у него нет вовсе — загрузку делают `ChatThread`/`ChatList`), отправка
// допустима с пустым текстом при наличии файла, а неудачная отправка не стирает
// ни текст, ни чипы. Что до отправки не уходит ни одного запроса — сторожат
// суиты выше по стеку, где сеть наблюдаема (`ChatList.test.tsx`, A13).

function file(name: string, size = 2048): File {
  return new File(["x".repeat(size)], name, { type: "text/markdown" });
}

function renderComposer(
  onSend: (content: string, files: File[]) => void | Promise<boolean>,
) {
  return renderWithProviders(<ChatInput onSend={onSend} />);
}

describe("ChatInput — вложения до отправки", () => {
  it("показывает прикреплённый файл чипом с именем и размером", () => {
    const onSend = vi.fn();
    const { container } = renderComposer(onSend);

    attach(container, file("konspekt.md", 2048));

    expect(screen.getByText("konspekt.md")).toBeInTheDocument();
    expect(screen.getByText("2 КБ")).toBeInTheDocument();
    // Ничего не отправлено: прикрепление — не отправка.
    expect(onSend).not.toHaveBeenCalled();
  });

  it("✕ до отправки убирает чип и не заводит отправку", async () => {
    // A13, половина композера: снятие чипа — операция над состоянием, отправку
    // она не заводит. Что при этом не уходит ни одного запроса, видно только
    // там, где загрузка живёт (`ChatList.test.tsx` § «✕ до отправки убирает
    // файл, не тронув сервер»): у `ChatInput` сетевого пути нет.
    const onSend = vi.fn();
    const { container } = renderComposer(onSend);
    attach(container, file("konspekt.md"));

    await userEvent.click(
      screen.getByRole("button", { name: "Убрать konspekt.md" }),
    );

    expect(screen.queryByText("konspekt.md")).not.toBeInTheDocument();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("держит два одноимённых файла независимыми чипами", () => {
    const { container } = renderComposer(vi.fn());

    attach(container, file("notes.md"), file("notes.md"));

    expect(screen.getAllByText("notes.md")).toHaveLength(2);
    expect(
      screen.getAllByRole("button", { name: "Убрать notes.md" }),
    ).toHaveLength(2);
  });

  it("не даёт отправить пустой композер", () => {
    renderComposer(vi.fn());

    expect(screen.getByRole("button", { name: "Отправить" })).toBeDisabled();
  });

  it("разрешает отправку с пустым текстом, если есть вложение", async () => {
    // § Тайминг: «отправка (текст может быть пустым)» — файл сам по себе
    // содержателен, требовать к нему текст незачем.
    const onSend = vi.fn();
    const { container } = renderComposer(onSend);
    attach(container, file("konspekt.md"));

    const send = screen.getByRole("button", { name: "Отправить" });
    expect(send).toBeEnabled();
    await userEvent.click(send);

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("", [
      expect.objectContaining({ name: "konspekt.md" }),
    ]);
  });

  it("отдаёт текст и файлы одной отправкой и очищает композер на успехе", async () => {
    const onSend = vi.fn(() => Promise.resolve(true));
    const { container } = renderComposer(onSend);
    const field = screen.getByPlaceholderText("Сообщение...");

    await userEvent.type(field, "Разбери конспект");
    attach(container, file("konspekt.md"));
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    await waitFor(() => expect(field).toHaveValue(""));
    expect(screen.queryByText("konspekt.md")).not.toBeInTheDocument();
    expect(onSend).toHaveBeenCalledWith("Разбери конспект", [
      expect.objectContaining({ name: "konspekt.md" }),
    ]);
  });

  it("на неудачной отправке сохраняет и текст, и чипы для повторной попытки", async () => {
    // A14: файл сверх лимита не должен стоить пользователю набранного текста —
    // он убирает лишний чип и жмёт «Отправить» ещё раз.
    const onSend = vi.fn(() => Promise.resolve(false));
    const { container } = renderComposer(onSend);
    const field = screen.getByPlaceholderText("Сообщение...");

    await userEvent.type(field, "Разбери конспект");
    attach(container, file("huge.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Отправить" }));

    await waitFor(() => expect(onSend).toHaveBeenCalledTimes(1));
    expect(field).toHaveValue("Разбери конспект");
    expect(screen.getByText("huge.pdf")).toBeInTheDocument();
  });

  it("не заводит вторую отправку той же партии, пока идёт первая", async () => {
    // Окно между кликом и стартом хода занято загрузкой файлов — повторный
    // клик здесь загрузил бы те же файлы во второй раз и завёл второй ход.
    let release!: () => void;
    const held = new Promise<boolean>((resolve) => {
      release = () => resolve(true);
    });
    const onSend = vi.fn(() => held);
    const { container } = renderComposer(onSend);
    attach(container, file("konspekt.md"));

    const send = screen.getByRole("button", { name: "Отправить" });
    await userEvent.click(send);
    await waitFor(() => expect(send).toBeDisabled());
    fireEvent.click(send);

    expect(onSend).toHaveBeenCalledTimes(1);
    // Пока идёт загрузка, чип уже не снять — файл уезжает на сервер.
    expect(
      screen.getByRole("button", { name: "Убрать konspekt.md" }),
    ).toBeDisabled();

    release();
    await waitFor(() =>
      expect(screen.queryByText("konspekt.md")).not.toBeInTheDocument(),
    );
  });
});

describe("ChatInput — drag&drop", () => {
  function dataTransfer(files: File[]) {
    return {
      files,
      items: files.map(() => ({ kind: "file" })),
      types: ["Files"],
    };
  }

  it("показывает подсказку, пока файл тянут над композером", () => {
    renderComposer(vi.fn());
    const field = screen.getByPlaceholderText("Сообщение...");

    fireEvent.dragEnter(field, { dataTransfer: dataTransfer([file("a.md")]) });

    expect(screen.getByText("Отпустите, чтобы прикрепить")).toBeInTheDocument();
  });

  it("не гасит подсказку, когда курсор переходит между частями композера", () => {
    // `dragenter`/`dragleave` всплывают с каждого вложенного узла: без счёта
    // глубины подсказка мигала бы при движении курсора внутри композера.
    renderComposer(vi.fn());
    const field = screen.getByPlaceholderText("Сообщение...");
    const send = screen.getByRole("button", { name: "Отправить" });
    const dt = dataTransfer([file("a.md")]);

    fireEvent.dragEnter(field, { dataTransfer: dt });
    fireEvent.dragEnter(send, { dataTransfer: dt });
    fireEvent.dragLeave(send, { dataTransfer: dt });

    expect(screen.getByText("Отпустите, чтобы прикрепить")).toBeInTheDocument();

    fireEvent.dragLeave(field, { dataTransfer: dt });

    expect(
      screen.queryByText("Отпустите, чтобы прикрепить"),
    ).not.toBeInTheDocument();
  });

  it("брошенный файл становится чипом, подсказка исчезает", () => {
    renderComposer(vi.fn());
    const field = screen.getByPlaceholderText("Сообщение...");
    const dropped = file("lecture.pdf", 1024);

    fireEvent.dragEnter(field, { dataTransfer: dataTransfer([dropped]) });
    fireEvent.drop(field, { dataTransfer: dataTransfer([dropped]) });

    expect(screen.getByText("lecture.pdf")).toBeInTheDocument();
    expect(
      screen.queryByText("Отпустите, чтобы прикрепить"),
    ).not.toBeInTheDocument();
  });
});
