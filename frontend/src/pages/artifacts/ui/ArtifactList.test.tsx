import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { ArtifactList } from "./ArtifactList";

// Integration: the project artifacts list. Reads :id from the route, fetches
// /projects/:id/artifacts, and renders loading / error / empty / populated
// states. Each artifact is a Link to `?path=`, so the page must be mounted
// in a router.

const ARTIFACTS_URL = "/api/projects/p1/artifacts";

function render() {
  return renderWithProviders(
    routerAt(<ArtifactList />, {
      path: "/projects/:id/artifacts",
      entry: "/projects/p1/artifacts",
    }),
  );
}

describe("ArtifactList", () => {
  it("lists artifacts returned by the API", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({
          items: [
            {
              path: "lecture-notes.md",
              title: "Lecture notes",
              type: "md",
              updated_at: "2026-02-01T12:00:00Z",
            },
            {
              path: "flashcards.md",
              title: "Flashcards",
              type: "md",
              updated_at: "2026-02-02T12:00:00Z",
            },
          ],
          total: 2,
          limit: 200,
          offset: 0,
        }),
      ),
    );

    render();

    expect(await screen.findByText("Lecture notes")).toBeInTheDocument();
    expect(screen.getByText("Flashcards")).toBeInTheDocument();
    // Each artifact links to the viewer via `?path=`.
    expect(screen.getByRole("link", { name: /Lecture notes/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts?path=lecture-notes.md",
    );
  });

  it("shows the empty state when there are no artifacts", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 }),
      ),
    );

    render();

    expect(await screen.findByText(/Артефактов пока нет/)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );

    render();

    expect(
      await screen.findByText("Ошибка загрузки артефактов."),
    ).toBeInTheDocument();
  });
});

// Бэкенд отдаёт плоский список полных путей (ADR-032) — вложенность собирает
// сам список. Проверяется то, что видит пользователь: директории как группы со
// счётчиком, файлы корня плоско, и открытый файл виден в дереве сразу, без
// ручного раскрытия предков.

function artifact(over: Partial<ArtifactRow> = {}): ArtifactRow {
  return {
    path: "notes.md",
    title: "Заметки",
    type: "md",
    updated_at: "2026-02-01T12:00:00Z",
    ...over,
  };
}

interface ArtifactRow {
  path: string;
  title: string;
  type: string;
  updated_at: string;
}

function listOf(items: ArtifactRow[]) {
  return http.get(ARTIFACTS_URL, () =>
    HttpResponse.json({
      items,
      total: items.length,
      limit: 200,
      offset: 0,
    }),
  );
}

function renderAt(search = "") {
  return renderWithProviders(
    routerAt(<ArtifactList />, {
      path: "/projects/:id/artifacts",
      entry: `/projects/p1/artifacts${search}`,
    }),
  );
}

describe("ArtifactList — дерево путей", () => {
  it("собирает директорию из вложенных путей и считает файлы всего поддерева", async () => {
    server.use(
      listOf([
        artifact({ path: "lecture-1/konspekt.md", title: "Конспект" }),
        artifact({ path: "lecture-1/slides/intro.md", title: "Вступление" }),
        artifact({ path: "readme.md", title: "Readme" }),
      ]),
    );

    renderAt();

    const dir = await screen.findByRole("button", { name: /lecture-1/ });
    // Счётчик — все файлы поддерева, а не только прямые потомки: иначе группа
    // с подпапками врала бы о своём объёме.
    expect(dir).toHaveTextContent("2");
    // Файл корня остаётся плоской строкой рядом с группой.
    expect(screen.getByRole("link", { name: /Readme/ })).toBeInTheDocument();
  });

  it("держит директорию свёрнутой, пока её не раскроют", async () => {
    server.use(
      listOf([artifact({ path: "lecture-1/konspekt.md", title: "Конспект" })]),
    );

    renderAt();

    const dir = await screen.findByRole("button", { name: /lecture-1/ });
    expect(dir).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Конспект")).not.toBeInTheDocument();

    await userEvent.click(dir);

    expect(dir).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: /Конспект/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts?path=lecture-1%2Fkonspekt.md",
    );
  });

  it("схлопывает раскрытую директорию обратно", async () => {
    server.use(
      listOf([artifact({ path: "lecture-1/konspekt.md", title: "Конспект" })]),
    );

    renderAt();
    const dir = await screen.findByRole("button", { name: /lecture-1/ });

    await userEvent.click(dir);
    await userEvent.click(dir);

    expect(dir).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Конспект")).not.toBeInTheDocument();
  });

  it("раскрывает предков открытого файла сразу, без ручного клика", async () => {
    // Переход по карточке чата и перезагрузка страницы приводят прямо к
    // вложенному пути: в свёрнутом дереве открытого файла не было бы видно.
    server.use(
      listOf([
        artifact({ path: "lecture-1/slides/intro.md", title: "Вступление" }),
        artifact({ path: "readme.md", title: "Readme" }),
      ]),
    );

    renderAt("?path=lecture-1%2Fslides%2Fintro.md");

    expect(
      await screen.findByRole("link", { name: /Вступление/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /lecture-1/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("button", { name: /slides/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("показывает свежие файлы корня выше давних", async () => {
    server.use(
      listOf([
        artifact({
          path: "old.md",
          title: "Давний",
          updated_at: "2026-01-01T10:00:00Z",
        }),
        artifact({
          path: "fresh.md",
          title: "Свежий",
          updated_at: "2026-03-01T10:00:00Z",
        }),
      ]),
    );

    renderAt();

    await screen.findByRole("link", { name: /Свежий/ });
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual(
      [expect.stringContaining("Свежий"), expect.stringContaining("Давний")],
    );
  });

  it("подписывает строку файла расширением и датой изменения", async () => {
    server.use(
      listOf([
        artifact({
          path: "plot.png",
          title: "График",
          type: "png",
          updated_at: "2026-02-03T12:00:00Z",
        }),
      ]),
    );

    renderAt();

    expect(await screen.findByText(/png · изменён/)).toBeInTheDocument();
  });
});
