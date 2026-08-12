import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { ArtifactList } from "./ArtifactList";

// Integration: the project artifacts list. Reads :id from the route, fetches
// /projects/:id/artifacts, and renders loading / error / empty / populated
// states. Each artifact is a Link, so the page must be mounted in a router.

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
              id: "a1",
              title: "Lecture notes",
              type: "summary",
              created_at: "2026-02-01T12:00:00Z",
            },
            {
              id: "a2",
              title: "Flashcards",
              type: "cards",
              created_at: "2026-02-02T12:00:00Z",
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
    // Each artifact links to its detail route.
    expect(screen.getByRole("link", { name: /Lecture notes/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts/a1",
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

  it("holds the panel with placeholders while it loads, without claiming it is empty", async () => {
    server.use(
      http.get(ARTIFACTS_URL, async () => {
        await delay(50);
        return HttpResponse.json({
          items: [],
          total: 0,
          limit: 200,
          offset: 0,
        });
      }),
    );

    const { container } = render();

    // Плашки скелетона не имеют доступного имени — берём публичный маркер
    // примитива дизайн-системы (`data-slot="skeleton"`), последнюю ступень
    // лестницы запросов из testing.md § Frontend. Геометрия строки и мерцание
    // в jsdom не исполняются, их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    expect(screen.queryByText(/Артефактов пока нет/)).not.toBeInTheDocument();

    await screen.findByText(/Артефактов пока нет/);
  });

  it("shows an error message when the request fails", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );

    render();

    expect(
      await screen.findByText("Не удалось загрузить артефакты."),
    ).toBeInTheDocument();
  });

  it("recovers the list from a failure through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(ARTIFACTS_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "nope" }, { status: 500 });
        }
        return HttpResponse.json({
          items: [
            {
              id: "a1",
              title: "Lecture notes",
              type: "summary",
              created_at: "2026-02-01T12:00:00Z",
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        });
      }),
    );
    const user = userEvent.setup();
    render();

    await screen.findByText("Не удалось загрузить артефакты.");
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Lecture notes")).toBeInTheDocument();
    expect(
      screen.queryByText("Не удалось загрузить артефакты."),
    ).not.toBeInTheDocument();
  });
});
