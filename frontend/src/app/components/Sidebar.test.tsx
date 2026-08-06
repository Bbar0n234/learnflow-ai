import "@/test/match-media-polyfill";

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

// The build-time SIEM flag is mocked at the module boundary rather than through
// `import.meta.env`: what the toggle parses out of the environment is pinned in
// `shared/config/feature-flags.test.ts`, and repeating it here would make every
// case depend on the string rules instead of on the gating behaviour. The mock
// is a getter so a single test file can render both bundles.
const flags = vi.hoisted(() => ({ siemEnabled: true }));

vi.mock("@/shared/config/feature-flags", () => ({
  get SIEM_ENABLED() {
    return flags.siemEnabled;
  },
  SHOW_GROUP_B_STUBS: false,
}));

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

beforeEach(() => {
  flags.siemEnabled = true;
});

afterEach(() => {
  localStorage.clear();
});

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

// Integration on the sidebar entry point into the Security UI (chore-001). Two
// independent conditions guard the button and the tests keep them independent:
// the build-time SIEM flag decides whether the feature exists in this bundle at
// all, and the admin claim decides whether this user may see it. Narrowing, not
// replacing — a non-admin must not get the button just because the flag is on.

const SECURITY_BUTTON = "Безопасность";

function emptyList() {
  return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 });
}

/** The sidebar's own queries — unrelated to the toggle, always answered. */
function stubSidebarNetwork({ isAdmin }: { isAdmin: boolean }) {
  server.use(
    http.get("/api/auth/me", () =>
      HttpResponse.json({ id: "u1", name: "tester", is_admin: isAdmin }),
    ),
    http.get("/api/projects", () => emptyList()),
    http.get("/api/chats/recent", () => emptyList()),
  );
}

async function renderSecuritySidebar({ isAdmin }: { isAdmin: boolean }) {
  stubSidebarNetwork({ isAdmin });

  renderWithProviders(
    <MemoryRouter initialEntries={["/"]}>
      <Sidebar />
    </MemoryRouter>,
  );

  // The user footer only appears once /auth/me has answered — waiting for it
  // means the admin claim is in before anything is asserted about the
  // admin-only button (otherwise the "no button" cases would pass trivially,
  // simply by asserting too early).
  await screen.findByText("tester");
}

describe("Sidebar — the Security entry point", () => {
  it("offers the Security button to an admin when the SIEM build is on", async () => {
    await renderSecuritySidebar({ isAdmin: true });

    expect(
      screen.getByRole("button", { name: SECURITY_BUTTON }),
    ).toBeInTheDocument();
  });

  it("hides the Security button from a non-admin even when the build is on", async () => {
    await renderSecuritySidebar({ isAdmin: false });

    expect(
      screen.queryByRole("button", { name: SECURITY_BUTTON }),
    ).not.toBeInTheDocument();
  });

  it("hides the Security button in a SIEM-off build even from an admin", async () => {
    flags.siemEnabled = false;

    await renderSecuritySidebar({ isAdmin: true });

    expect(
      screen.queryByRole("button", { name: SECURITY_BUTTON }),
    ).not.toBeInTheDocument();
  });

  it("leaves the rest of the sidebar untouched in a SIEM-off build", async () => {
    // The kill-switch removes one button, not the navigation around it: a
    // production build with SIEM off must still be an ordinary app.
    flags.siemEnabled = false;

    await renderSecuritySidebar({ isAdmin: true });

    expect(
      screen.getByRole("button", { name: /Новый чат/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Новый проект/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Проекты")).toBeInTheDocument();
  });
});
