import "@/test/match-media-polyfill";

import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";
import { renderWithProviders } from "@/test/test-utils";

// The build-time SIEM flag is mocked at the module boundary; its parsing rules
// are pinned in `shared/config/feature-flags.test.ts`. The mock is a getter so
// a single test file can render both bundles.
const flags = vi.hoisted(() => ({ siemEnabled: true }));

vi.mock("@/shared/config/feature-flags", () => ({
  get SIEM_ENABLED() {
    return flags.siemEnabled;
  },
  SHOW_GROUP_B_STUBS: false,
}));

import { AppRoutes } from "./router";

// Integration (feat-002, T2.6): the chat routes as the user reaches them —
// through the real route table, not by mounting a page component directly. The
// composer lives at its own URL `/projects/:id/chats/new` (design-brief §
// Создание чата и первое сообщение) and must land on the draft branch: without
// that route the `chats/:cid` pattern would swallow it with `cid = "new"` and
// try to load a chat that does not exist. Network is MSW with
// `onUnhandledRequest: "error"`, so such a request would fail the run.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";

function appHandlers() {
  return [
    http.get("/api/projects", () =>
      HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 }),
    ),
    http.get("/api/auth/me", () =>
      HttpResponse.json({ id: "u1", name: "tester", is_admin: false }),
    ),
    http.get("/api/chats/recent", () =>
      HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 }),
    ),
    http.get(`/api/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        id: PROJECT_ID,
        name: "Матан",
        created_at: "2026-07-01T10:00:00Z",
        updated_at: "2026-07-01T10:00:00Z",
      }),
    ),
  ];
}

function renderAppAt(entry: string) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

// jsdom has no layout — the message feed auto-scrolls a ref into view.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

beforeEach(() => {
  flags.siemEnabled = true;
});

afterEach(() => {
  localStorage.clear();
});

describe("AppRoutes — chat screens", () => {
  it("opens the composer on the new-chat URL, without touching a chat", async () => {
    setAccessToken(fakeJwt());
    server.use(...appHandlers());

    renderAppAt(`/projects/${PROJECT_ID}/chats/new`);

    expect(
      await screen.findByText(
        "Напишите первое сообщение — чат появится вместе с ним, а название придумает модель.",
      ),
    ).toBeInTheDocument();
  });

  it("opens the existing chat with its history on a chat URL", async () => {
    setAccessToken(fakeJwt());
    server.use(
      ...appHandlers(),
      http.get(`/api/projects/${PROJECT_ID}/chats/${CHAT_ID}`, () =>
        HttpResponse.json({
          thread_id: CHAT_ID,
          title: "Производные",
          security_blocked: false,
          messages: [
            {
              id: "m-1",
              role: "user",
              content: "Старое сообщение",
              created_at: "2026-07-01T10:00:00Z",
              artifacts: [],
            },
          ],
        }),
      ),
    );

    renderAppAt(`/projects/${PROJECT_ID}/chats/${CHAT_ID}`);

    expect(await screen.findByText("Старое сообщение")).toBeInTheDocument();
  });
});

// Integration on the route half of the SIEM kill-switch (chore-001): in a
// SIEM-off bundle `/security` must not exist as a route at all, and in a
// SIEM-on bundle it must still be there, behind its RBAC guard.
//
// `/security` is nested under the pathless app layout, so "the route is gone"
// is directly observable: with nothing matching, React Router renders neither
// the page nor the chrome around it and the tree comes out empty. The SIEM-on
// case is held at the guard's loading state (the profile request is delayed) —
// that is enough to prove the route matched, and it keeps the lazy Security
// page and its own network out of a test about routing.

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
