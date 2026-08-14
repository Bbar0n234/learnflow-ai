import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import type { Project } from "@/shared/api/projects";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ProjectList } from "./ProjectList";

// Integration (feat-013, трек T4): список проектов сайдбара во всех четырёх
// состояниях. Это самый узкий список продукта (252px), поэтому блоки 3 и 4
// брифа требуют от него ровно того же, что от широких: плейсхолдеры вместо
// строки «Loading...» на загрузке и карточку ошибки с «Повторить» вместо
// голой красной строки, которая не давала выхода кроме F5. Сеть — MSW,
// строки проектов — ссылки, поэтому список монтируется в роутере.

const PROJECTS_URL = "/api/projects";

function project(over: Partial<Project> = {}): Project {
  return {
    id: "p1",
    name: "Матан",
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    ...over,
  };
}

function projectsResponse(items: Project[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 200,
    offset: 0,
  });
}

function renderList() {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/"]}>
      <ProjectList />
    </MemoryRouter>,
  );
}

describe("ProjectList", () => {
  it("lists the projects as links into the project", async () => {
    server.use(http.get(PROJECTS_URL, () => projectsResponse([project()])));

    renderList();

    expect(await screen.findByRole("link", { name: /Матан/ })).toHaveAttribute(
      "href",
      "/projects/p1",
    );
  });

  it("holds the sidebar with placeholders while the projects load", async () => {
    server.use(
      http.get(PROJECTS_URL, async () => {
        await delay(50);
        return projectsResponse([]);
      }),
    );

    const { container } = renderList();

    // Плашки скелетона не имеют доступного имени — берём публичный маркер
    // примитива дизайн-системы (`data-slot="skeleton"`), последнюю ступень
    // лестницы запросов из testing.md § Frontend. Ширины плашек и мерцание
    // jsdom не исполняет: их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    // Пока данные в пути, отсутствие проектов не объявляется.
    expect(screen.queryByText("Проектов пока нет")).not.toBeInTheDocument();

    await screen.findByText("Проектов пока нет");
  });

  it("says the user has no projects yet, in Russian", async () => {
    server.use(http.get(PROJECTS_URL, () => projectsResponse([])));

    renderList();

    expect(await screen.findByText("Проектов пока нет")).toBeInTheDocument();
  });

  it("offers a way back from a failure instead of a dead red line", async () => {
    server.use(
      http.get(PROJECTS_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderList();

    expect(
      await screen.findByText("Не удалось загрузить проекты"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Повторить" }),
    ).toBeInTheDocument();
  });

  it("recovers the sidebar list through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(PROJECTS_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return projectsResponse([project()]);
      }),
    );
    const user = userEvent.setup();
    renderList();

    await screen.findByText("Не удалось загрузить проекты");
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("link", { name: /Матан/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Не удалось загрузить проекты"),
    ).not.toBeInTheDocument();
  });
});
