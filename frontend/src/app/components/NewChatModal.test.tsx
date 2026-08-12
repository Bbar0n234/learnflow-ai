import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { Project } from "@/shared/api/projects";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { NewChatModal } from "./NewChatModal";

// Integration (feat-002, T2.7): the «+ Новый чат» entry from the sidebar. The
// project picker is shown every time — a chat always belongs to a project and
// the user may want it in a different one than the screen they are on
// (design-brief § Целевой UX). Picking a project leads to the composer; no chat
// is created at this point (MSW fails on unhandled requests, so a stray
// `POST /chats` would fail the test). A user with no projects gets an
// empty-state that creates a project and lands straight in its composer.

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

function ComposerProbe() {
  const location = useLocation();
  return <p>Композер: {location.pathname}</p>;
}

function renderModal(entry = "/settings") {
  const onOpenChange = vi.fn();
  const modal = <NewChatModal open onOpenChange={onOpenChange} />;
  const view = renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/settings" element={modal} />
        <Route path="/projects/:id" element={modal} />
        <Route path="/projects/:id/chats/new" element={<ComposerProbe />} />
      </Routes>
    </MemoryRouter>,
  );
  return { ...view, onOpenChange };
}

// The picker shows up on any screen: outside a project (the sidebar button
// works from anywhere) and inside one — the user may well want the chat in a
// different project than the page they are on (design-brief § Целевой UX).
const ENTRY_SCREENS = ["/settings", "/projects/p1"];

describe("NewChatModal", () => {
  it.each(ENTRY_SCREENS)(
    "asks which project the chat belongs to, from %s",
    async (entry) => {
      server.use(http.get(PROJECTS_URL, () => projectsResponse([project()])));

      renderModal(entry);

      expect(await screen.findByText("Новый чат")).toBeInTheDocument();
      expect(
        screen.getByText("Выберите проект, в котором начать чат."),
      ).toBeInTheDocument();
    },
  );

  it.each(ENTRY_SCREENS)(
    "opens the composer of the picked project without creating a chat, from %s",
    async (entry) => {
      server.use(
        http.get(PROJECTS_URL, () =>
          projectsResponse([project(), project({ id: "p2", name: "Физика" })]),
        ),
      );
      const user = userEvent.setup();
      const { onOpenChange } = renderModal(entry);

      // Deliberately a different project than the one the entry screen is on.
      await user.click(await screen.findByRole("button", { name: /Физика/ }));

      expect(
        await screen.findByText("Композер: /projects/p2/chats/new"),
      ).toBeInTheDocument();
      expect(onOpenChange).toHaveBeenCalledWith(false);
    },
  );

  it("shows a loading hint while the projects are in flight", async () => {
    server.use(
      http.get(PROJECTS_URL, async () => {
        await delay(50);
        return projectsResponse([]);
      }),
    );

    renderModal();

    expect(screen.getByText("Загрузка проектов…")).toBeInTheDocument();
    // Let the request land before the test ends — one still in flight at
    // teardown resolves into a torn-down environment.
    expect(
      await screen.findByText(
        "У вас пока нет проектов — чат живёт внутри проекта.",
      ),
    ).toBeInTheDocument();
  });

  it("reports a failure to load the projects", async () => {
    server.use(
      http.get(PROJECTS_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderModal();

    expect(
      await screen.findByText("Не удалось загрузить список проектов"),
    ).toBeInTheDocument();
  });

  it("recovers the project picker through «Повторить»", async () => {
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
    renderModal();

    await screen.findByText("Не удалось загрузить список проектов");
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери, и
    // выбор проекта становится возможен без перезагрузки страницы.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("button", { name: /Матан/ }),
    ).toBeInTheDocument();
  });

  it("explains to a user without projects that a chat lives inside one", async () => {
    server.use(http.get(PROJECTS_URL, () => projectsResponse([])));

    renderModal();

    expect(
      await screen.findByText(
        "У вас пока нет проектов — чат живёт внутри проекта.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Создать проект/ }),
    ).toBeInTheDocument();
  });

  it("lands in the composer of a project created from the empty state", async () => {
    server.use(
      http.get(PROJECTS_URL, () => projectsResponse([])),
      http.post(PROJECTS_URL, () =>
        HttpResponse.json(project({ id: "p-new", name: "Химия" }), {
          status: 201,
        }),
      ),
    );
    const user = userEvent.setup();
    renderModal();

    await user.click(
      await screen.findByRole("button", { name: /Создать проект/ }),
    );
    await user.type(
      await screen.findByPlaceholderText("Название проекта"),
      "Химия",
    );
    await user.click(screen.getByRole("button", { name: "Создать" }));

    // Straight to the composer — no detour through the project page.
    expect(
      await screen.findByText("Композер: /projects/p-new/chats/new"),
    ).toBeInTheDocument();
  });
});
