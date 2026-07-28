import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

// jsdom has no `matchMedia`, and the theme store resolves the initial theme
// from it at module load — stub it before the sidebar's imports run.
vi.hoisted(() => {
  if (typeof window !== "undefined" && !window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

import { Sidebar } from "./Sidebar";

// Integration (feat-002, T2.7): the sidebar's «+ Новый чат» entry. The button
// used to be disabled outside a project and created a chat on the spot; it is
// now available from any screen and only opens the project picker — the chat
// itself is created when the first message is sent (design-brief § Целевой UX).
// Recent chats carry the same row menu as the project chat list. Network is MSW
// with `onUnhandledRequest: "error"`, so a chat created here would fail the run.

function baseHandlers() {
  return [
    http.get("/api/projects", () =>
      HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 }),
    ),
    http.get("/api/auth/me", () =>
      HttpResponse.json({ id: "u1", name: "tester", is_admin: false }),
    ),
    http.get("/api/chats/recent", () =>
      HttpResponse.json({
        items: [
          {
            thread_id: "c1",
            title: "Производные",
            project_id: "p1",
            project_name: "Матан",
            updated_at: "2026-07-01T10:00:00Z",
            security_blocked: false,
          },
        ],
        total: 1,
        limit: 10,
        offset: 0,
      }),
    ),
  ];
}

function renderSidebar(entry = "/settings") {
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <Sidebar />
    </MemoryRouter>,
  );
}

/**
 * The row menu trigger sits alongside the chat link, not inside it. It is an
 * icon-only button (no accessible name), so it is found by walking up from the
 * link until an ancestor holds a button outside of it — that keeps the query on
 * the behaviour ("next to the link") rather than on the row's exact nesting.
 */
function rowMenuTriggerFor(link: HTMLElement): HTMLElement {
  for (let row = link.parentElement; row; row = row.parentElement) {
    const trigger = within(row)
      .queryAllByRole("button")
      .find((button) => !link.contains(button));
    if (trigger) return trigger;
  }
  throw new Error("Меню строки чата не найдено рядом со ссылкой");
}

// Both entry screens matter: outside any project (where the button used to be
// disabled) and inside a project (where it used to create a chat on the spot,
// bypassing the picker). The contract is the same on both — «модалка выбора
// проекта показывается всегда, в том числе когда пользователь уже внутри
// проекта» (design-brief § Целевой UX).
const ENTRY_SCREENS = ["/settings", "/projects/p1"];

describe("Sidebar", () => {
  it.each(ENTRY_SCREENS)("offers a new chat from %s", async (entry) => {
    server.use(...baseHandlers());

    renderSidebar(entry);

    expect(
      await screen.findByRole("button", { name: /Новый чат/ }),
    ).toBeEnabled();
  });

  it.each(ENTRY_SCREENS)(
    "asks for a project instead of creating a chat right away, from %s",
    async (entry) => {
      server.use(...baseHandlers());
      const user = userEvent.setup();
      renderSidebar(entry);

      await user.click(
        await screen.findByRole("button", { name: /Новый чат/ }),
      );

      // A chat created here would hit an unhandled `POST …/chats` and fail the
      // run (MSW `onUnhandledRequest: "error"`) — including on the project
      // screen, where the old behaviour created one immediately.
      expect(
        await screen.findByText("Выберите проект, в котором начать чат."),
      ).toBeInTheDocument();
    },
  );

  it("puts a row menu on every recent chat", async () => {
    server.use(...baseHandlers());
    const user = userEvent.setup();
    renderSidebar("/settings");

    const recent = await screen.findByRole("link", { name: /Производные/ });
    // Opening the menu must not navigate into the chat — the trigger lives
    // next to the link, not inside it.
    await user.click(rowMenuTriggerFor(recent));

    expect(
      await screen.findByRole("menuitem", { name: "Переименовать" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Удалить" }),
    ).toBeInTheDocument();
  });
});
