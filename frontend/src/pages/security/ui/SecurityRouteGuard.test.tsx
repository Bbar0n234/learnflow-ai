import { screen } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { SecurityRouteGuard } from "./SecurityRouteGuard";

// Integration: the RBAC guard for /security. It admits the user when /auth/me (or
// the JWT is_admin claim) marks them admin, and redirects to "/" otherwise.
// Network is MSW; routing observed via a MemoryRouter whose "/" route is a marker.

const ME_URL = "/api/auth/me";

/** A non-expired JWT carrying an optional is_admin claim. */
function jwt(claims: Record<string, unknown> = {}): string {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600, ...claims }),
  );
  return `${header}.${payload}.signature`;
}

function renderGuard(child: ReactNode = <div>Secret dashboard</div>) {
  return renderWithProviders(
    <MemoryRouter initialEntries={["/security"]}>
      <Routes>
        <Route path="/" element={<div>Home page</div>} />
        <Route
          path="/security"
          element={<SecurityRouteGuard>{child}</SecurityRouteGuard>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  localStorage.clear();
});

describe("SecurityRouteGuard", () => {
  it("renders the guarded content for an admin (per /auth/me)", async () => {
    setAccessToken(jwt());
    server.use(
      http.get(ME_URL, () =>
        HttpResponse.json({ id: "u1", name: "admin", is_admin: true }),
      ),
    );

    renderGuard();

    expect(await screen.findByText("Secret dashboard")).toBeInTheDocument();
  });

  it("redirects a non-admin to the home route", async () => {
    setAccessToken(jwt());
    server.use(
      http.get(ME_URL, () =>
        HttpResponse.json({ id: "u2", name: "user", is_admin: false }),
      ),
    );

    renderGuard();

    expect(await screen.findByText("Home page")).toBeInTheDocument();
    expect(screen.queryByText("Secret dashboard")).not.toBeInTheDocument();
  });

  it("shows a loading state while the profile is in flight", async () => {
    setAccessToken(jwt());
    server.use(
      http.get(ME_URL, async () => {
        await delay(50);
        return HttpResponse.json({ id: "u1", name: "admin", is_admin: true });
      }),
    );

    renderGuard();

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
    await screen.findByText("Secret dashboard");
  });

  it("admits a user whose JWT carries the is_admin claim even if /auth/me omits it", async () => {
    setAccessToken(jwt({ is_admin: true }));
    server.use(
      http.get(ME_URL, () =>
        HttpResponse.json({ id: "u3", name: "claims-admin", is_admin: false }),
      ),
    );

    renderGuard();

    expect(await screen.findByText("Secret dashboard")).toBeInTheDocument();
  });
});
