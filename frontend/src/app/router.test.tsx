import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";
import { renderWithProviders } from "@/test/test-utils";

// jsdom has no `matchMedia`, and the theme store resolves the initial theme
// from it at module load — stub it before the app's imports run.
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
