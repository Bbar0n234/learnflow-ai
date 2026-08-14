import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { ArtifactView } from "./ArtifactView";

// Integration: вьюер артефакта файловой модели (feat-011, T2.2). Адрес — путь в
// query-параметре (`?path=`), вид вьюера выбирает словарь расширений, а не
// семантический тип, и исчезнувший файл обязан читаться как отдельное
// состояние, а не как «ошибка загрузки»: путь перезаписываем и переименовываем
// (ADR-032), ссылка из истории устаревает штатно. Сеть — MSW.

const DETAIL_URL = "/api/projects/p1/artifacts";
const MEDIA_URL = "/api/projects/p1/artifacts/media";
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

interface Detail {
  path: string;
  title: string;
  type: string;
  updated_at: string;
  content?: string;
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock/image");
  URL.revokeObjectURL = vi.fn();
});

function detailHandler(detail: Detail, seen?: { path: string | null }) {
  return http.get(DETAIL_URL, ({ request }) => {
    if (seen) seen.path = new URL(request.url).searchParams.get("path");
    return HttpResponse.json(detail);
  });
}

function renderViewer(path: string) {
  return renderWithProviders(
    routerAt(<ArtifactView />, {
      path: "/projects/:id/artifacts",
      entry: `/projects/p1/artifacts?path=${encodeURIComponent(path)}`,
    }),
  );
}

describe("ArtifactView — вид по расширению", () => {
  it("markdown-артефакт показывает содержимое и скачивание по своему расширению", async () => {
    server.use(
      detailHandler({
        path: "konspekt.md",
        title: "Конспект",
        type: "md",
        updated_at: "2026-02-01T12:00:00Z",
        content: "# Заголовок конспекта",
      }),
    );

    renderViewer("konspekt.md");

    expect(await screen.findByText("Заголовок конспекта")).toBeInTheDocument();
    expect(screen.getByText(/md · изменён/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: ".md" })).toBeInTheDocument();
  });

  it("экспорта в PDF во вьюере нет", async () => {
    // C3: `download?format=pdf` из REST-контракта ушёл — кнопка, обещающая
    // несуществующий экспорт, обязана уйти вместе с ним.
    server.use(
      detailHandler({
        path: "konspekt.md",
        title: "Конспект",
        type: "md",
        updated_at: "2026-02-01T12:00:00Z",
        content: "текст",
      }),
    );

    renderViewer("konspekt.md");

    await screen.findByText("текст");
    expect(
      screen.queryByRole("button", { name: /pdf/i }),
    ).not.toBeInTheDocument();
  });

  it("нераспознанное текстовое расширение показывает тело файла как текст", async () => {
    // Штатный выход `write_file`/джобы: `.csv`/`.py`/`.json` — не бинарник и
    // не markdown, но читать его содержимое пользователь всё равно должен.
    server.use(
      detailHandler({
        path: "stats.csv",
        title: "stats.csv",
        type: "csv",
        updated_at: "2026-02-01T12:00:00Z",
        content: "имя,значение\nсредняя,4.2",
      }),
    );

    renderViewer("stats.csv");

    expect(await screen.findByText(/средняя,4.2/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: ".csv" })).toBeInTheDocument();
  });

  it("бинарный файл без содержимого предлагает скачивание вместо ошибки", async () => {
    // Detail бинарного отдаёт только метаданные (C3) — это нормальное
    // состояние файла, а не сбой, и читаться оно должно именно так.
    server.use(
      detailHandler({
        path: "lecture.pdf",
        title: "Лекция",
        type: "pdf",
        updated_at: "2026-02-01T12:00:00Z",
      }),
    );

    renderViewer("lecture.pdf");

    expect(
      await screen.findByText("Предпросмотр недоступен — бинарный файл."),
    ).toBeInTheDocument();
    expect(screen.getByText("Лекция")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Скачать/ })).toBeInTheDocument();
  });

  it("png открывается картинкой, а не заглушкой бинарника", async () => {
    server.use(
      detailHandler({
        path: "lecture-1/plot.png",
        title: "График",
        type: "png",
        updated_at: "2026-02-01T12:00:00Z",
      }),
      http.get(
        MEDIA_URL,
        () =>
          new HttpResponse(PNG_BYTES, {
            headers: { "Content-Type": "image/png" },
          }),
      ),
    );

    renderViewer("lecture-1/plot.png");

    expect(await screen.findByAltText("График")).toHaveAttribute(
      "src",
      "blob:mock/image",
    );
    expect(
      screen.queryByText("Предпросмотр недоступен — бинарный файл."),
    ).not.toBeInTheDocument();
  });
});

describe("ArtifactView — адресация и состояния отсутствия", () => {
  it("запрашивает артефакт полным путём, включая поддиректории", async () => {
    // A5: вложенность держится query-параметром — сегмент URL со слэшем не
    // сматчился бы роутом и разъехался бы с REST.
    const seen = { path: null as string | null };
    server.use(
      detailHandler(
        {
          path: "lecture-1/slides.md",
          title: "Слайды",
          type: "md",
          updated_at: "2026-02-01T12:00:00Z",
          content: "слайд",
        },
        seen,
      ),
    );

    renderViewer("lecture-1/slides.md");

    await screen.findByText("слайд");
    expect(seen.path).toBe("lecture-1/slides.md");
  });

  it("исчезнувший файл объясняет себя путём, а не красной ошибкой", async () => {
    // A6c: агент переименовал или удалил файл — ссылка из истории устарела.
    // Это ожидаемое свойство файловой идентичности, и текст обязан это сказать.
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ detail: "not found" }, { status: 404 }),
      ),
    );

    renderViewer("lecture-1/deleted.md");

    expect(
      await screen.findByText("Файл больше не существует"),
    ).toBeInTheDocument();
    expect(screen.getByText("lecture-1/deleted.md")).toBeInTheDocument();
    expect(
      screen.queryByText("Не удалось загрузить артефакт."),
    ).not.toBeInTheDocument();
  });

  it("сбой сервера остаётся ошибкой загрузки, а не «файла больше нет»", async () => {
    // Обратная сторона предыдущего кейса: 5xx — это «попробуйте позже», и
    // подменять его сообщением об удалении файла значило бы соврать.
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderViewer("konspekt.md");

    // Форма ошибки — общий канон состояний (feat-013): заголовок + подпись
    // вместо прежней инлайн-строки. Кейс сторожит не текст, а различение веток.
    expect(
      await screen.findByRole("heading", {
        name: "Не удалось загрузить артефакт",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Файл больше не существует"),
    ).not.toBeInTheDocument();
  });
});

// Integration (feat-013, трек T4): панель артефакта в переходных состояниях.
// Загрузка и ошибка — «панельная» половина канона состояний: спиннер с русской
// подписью вместо голой строки и полноэкранная карточка ошибки, из которой есть
// выход помимо F5. Форма общая с чатом и сферой — разнобой между панелями и был
// тем, против чего канон заведён. Ветка «файла больше нет» (404) отдельная и
// проверяется выше: это не ошибка загрузки.
describe("ArtifactView — переходные состояния панели", () => {
  const DETAIL: Detail = {
    path: "konspekt.md",
    title: "Конспект",
    type: "md",
    updated_at: "2026-02-01T12:00:00Z",
    content: "Тело конспекта",
  };

  it("сообщает о загрузке подписью панели, а не голой строкой", async () => {
    server.use(
      http.get(DETAIL_URL, async () => {
        await delay(50);
        return HttpResponse.json(DETAIL);
      }),
    );

    renderViewer("konspekt.md");

    expect(screen.getByText("Загрузка артефакта…")).toBeInTheDocument();

    await screen.findByText("Тело конспекта");
  });

  it("объясняет неудачную загрузку и даёт из неё выход", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderViewer("konspekt.md");

    expect(
      await screen.findByRole("heading", {
        name: "Не удалось загрузить артефакт",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Проверьте соединение и попробуйте ещё раз/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Повторить" }),
    ).toBeInTheDocument();
  });

  it("возвращает артефакт по «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(DETAIL_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json(DETAIL);
      }),
    );
    const user = userEvent.setup();

    renderViewer("konspekt.md");

    await screen.findByRole("heading", {
      name: "Не удалось загрузить артефакт",
    });
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Тело конспекта")).toBeInTheDocument();
  });
});
