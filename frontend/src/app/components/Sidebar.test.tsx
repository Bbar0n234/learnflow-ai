import "@/test/match-media-polyfill";

import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

// Integration on the sidebar entry point into the Security UI. Two independent
// conditions guard the button and the test keeps them independent: the build-
// time SIEM flag decides whether the feature exists in this bundle at all, and
// the admin claim decides whether this user may see it. Narrowing, not
// replacing — a non-admin must not get the button just because the flag is on.
//
// The flag is mocked at the module boundary rather than through
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

async function renderSidebar({ isAdmin }: { isAdmin: boolean }) {
  stubSidebarNetwork({ isAdmin });
  const { Sidebar } = await import("./Sidebar");

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

beforeEach(() => {
  flags.siemEnabled = true;
});

afterEach(() => {
  localStorage.clear();
});

describe("Sidebar — the Security entry point", () => {
  it("offers the Security button to an admin when the SIEM build is on", async () => {
    await renderSidebar({ isAdmin: true });

    expect(
      screen.getByRole("button", { name: SECURITY_BUTTON }),
    ).toBeInTheDocument();
  });

  it("hides the Security button from a non-admin even when the build is on", async () => {
    await renderSidebar({ isAdmin: false });

    expect(
      screen.queryByRole("button", { name: SECURITY_BUTTON }),
    ).not.toBeInTheDocument();
  });

  it("hides the Security button in a SIEM-off build even from an admin", async () => {
    flags.siemEnabled = false;

    await renderSidebar({ isAdmin: true });

    expect(
      screen.queryByRole("button", { name: SECURITY_BUTTON }),
    ).not.toBeInTheDocument();
  });

  it("leaves the rest of the sidebar untouched in a SIEM-off build", async () => {
    // The kill-switch removes one button, not the navigation around it: a
    // production build with SIEM off must still be an ordinary app.
    flags.siemEnabled = false;

    await renderSidebar({ isAdmin: true });

    expect(
      screen.getByRole("button", { name: /Новый чат/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Новый проект/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("Проекты")).toBeInTheDocument();
  });
});
