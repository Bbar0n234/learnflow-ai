import "@/test/match-media-polyfill";

import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { AppRoutes } from "./router";

// Integration on the route half of the SIEM kill-switch: in a SIEM-off bundle
// `/security` must not exist as a route at all, and in a SIEM-on bundle it must
// still be there, behind its RBAC guard.
//
// `/security` is nested under the pathless app layout, so "the route is gone"
// is directly observable: with nothing matching, React Router renders neither
// the page nor the chrome around it and the tree comes out empty. The SIEM-on
// case is held at the guard's loading state (the profile request is delayed) —
// that is enough to prove the route matched, and it keeps the lazy Security
// page and its own network out of a test about routing.
//
// The flag is mocked at the module boundary; its parsing rules are pinned in
// `shared/config/feature-flags.test.ts`.

const flags = vi.hoisted(() => ({ siemEnabled: true }));

vi.mock("@/shared/config/feature-flags", () => ({
  get SIEM_ENABLED() {
    return flags.siemEnabled;
  },
  SHOW_GROUP_B_STUBS: false,
}));

const GUARD_LOADING = "Загрузка...";
const WELCOME_HEADING = "Добро пожаловать";

function emptyList() {
  return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 });
}

function stubAppNetwork() {
  server.use(
    // Delayed on purpose: the guard stays in its loading state, so the test
    // observes "the route rendered" without mounting the Security page.
    http.get("/api/auth/me", async () => {
      await delay(200);
      return HttpResponse.json({ id: "u1", name: "tester", is_admin: true });
    }),
    http.get("/api/projects", () => emptyList()),
    http.get("/api/chats/recent", () => emptyList()),
  );
}

function renderAt(entry: string) {
  stubAppNetwork();
  // The RBAC guard only queries the profile when a token is present; without
  // one it redirects immediately and the loading state never appears.
  setAccessToken("header.payload.signature");
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  flags.siemEnabled = true;
});

afterEach(() => {
  localStorage.clear();
});

describe("AppRoutes — the /security route under the SIEM flag", () => {
  it("routes /security to the guarded Security page in a SIEM-on build", async () => {
    renderAt("/security");

    expect(await screen.findByText(GUARD_LOADING)).toBeInTheDocument();
  });

  it("has no /security route at all in a SIEM-off build", () => {
    flags.siemEnabled = false;

    const { container } = renderAt("/security");

    // Nothing matches, so not even the app layout renders — the deep link is a
    // dead end rather than an empty Security page.
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(GUARD_LOADING)).not.toBeInTheDocument();
  });

  it("keeps every other route working in a SIEM-off build", async () => {
    // The kill-switch removes one route, not the router: the rest of the app
    // must be indistinguishable from a SIEM-on build.
    flags.siemEnabled = false;

    renderAt("/");

    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
  });
});
