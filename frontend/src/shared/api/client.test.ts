import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";

import type * as ClientModule from "./client";

// Token storage + proactive SSE-token refresh. ensureFreshToken decodes the JWT
// exp and only hits /auth/refresh when the token is near expiry; the refresh
// endpoint is mocked via MSW.

// The response interceptor keeps its single-flight state (the "a refresh is in
// flight" flag and the queue of requests waiting behind it) in module scope, so
// a case that left the module mid-flight would leak into the next one — a
// runaway case would then paint its neighbours red with the wrong attribution.
// Re-creating the module registry per case makes the isolation structural
// instead of trusting every case to unwind its own promises; nothing is
// exported from the production module for the sake of the test.
let client!: typeof ClientModule;

beforeEach(async () => {
  vi.resetModules();
  client = await import("./client");
});

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("access token storage", () => {
  it("round-trips a token through localStorage", () => {
    expect(client.getAccessToken()).toBeNull();

    client.setAccessToken("tok-123");
    expect(client.getAccessToken()).toBe("tok-123");

    client.clearAccessToken();
    expect(client.getAccessToken()).toBeNull();
  });
});

describe("ensureFreshToken", () => {
  it("returns null when there is no token", async () => {
    expect(await client.ensureFreshToken()).toBeNull();
  });

  it("returns the current token when it is far from expiry, without refreshing", async () => {
    const token = fakeJwt(3600);
    client.setAccessToken(token);

    expect(await client.ensureFreshToken()).toBe(token);
  });

  it("clears a malformed token and returns null", async () => {
    client.setAccessToken("not-a-jwt");

    expect(await client.ensureFreshToken()).toBeNull();
    expect(client.getAccessToken()).toBeNull();
  });

  it("refreshes and stores a new token when the current one is near expiry", async () => {
    server.use(
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ access_token: "refreshed-token" }),
      ),
    );
    client.setAccessToken(fakeJwt(10)); // expires in ~10s, under the 30s threshold

    const result = await client.ensureFreshToken();

    expect(result).toBe("refreshed-token");
    expect(client.getAccessToken()).toBe("refreshed-token");
  });

  it("clears the token and reloads the app when the near-expiry refresh fails", async () => {
    // The negative half of the same critical path: the SSE/fetch callers get
    // null (no stale credentials handed out), the dead token is dropped and the
    // app restarts on the login screen instead of streaming with a bad token.
    server.use(
      http.post(
        "/api/auth/refresh",
        () => new HttpResponse(null, { status: 401 }),
      ),
    );
    const reload = stubReload();
    client.setAccessToken(fakeJwt(10));

    expect(await client.ensureFreshToken()).toBeNull();

    expect(client.getAccessToken()).toBeNull();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});

// The 401 branch of the response interceptor (feat-013 § 10). The contract is
// semantic, not textual: a 401 means "my access token is stale" for every call
// made on behalf of an already-authenticated user — including /auth/me and
// /auth/logout — so it must go through the single-flight refresh and be
// retried. Only the endpoints that issue or renew credentials without a valid
// access token (/auth/refresh, /auth/login, /auth/register) stay out of that
// flow; /auth/refresh in particular, because retrying it through itself would
// recurse. The bug this suite guards: /auth/me used to be excluded by a
// blanket "/auth/" substring test, so the sidebar's user query died on a cold
// session and its footer never rendered.
//
// Everything here talks to the real axios instance through MSW: the seam is the
// network, so the interceptor runs exactly as it does in the browser and no
// internal flag of it is ever inspected.

const STALE_TOKEN = "stale-token";
const FRESH_TOKEN = "fresh-token";

/**
 * A protected endpoint: 401 unless the request carries the refreshed token.
 * Asserting through it means the retry is only observable when it actually
 * re-sent the request with the new credentials.
 */
function protectedEndpoint(path: string, onUnauthorized?: () => void) {
  return http.all(`/api${path}`, ({ request }) => {
    if (request.headers.get("Authorization") === `Bearer ${FRESH_TOKEN}`) {
      return HttpResponse.json({ path });
    }
    onUnauthorized?.();
    return new HttpResponse(null, { status: 401 });
  });
}

/** POST /auth/refresh, counting calls so single-flight can be asserted. */
function stubRefresh(
  respond: () => Response | Promise<Response> = () =>
    HttpResponse.json({ access_token: FRESH_TOKEN }),
) {
  const refresh = { calls: 0 };
  server.use(
    http.post("/api/auth/refresh", () => {
      refresh.calls += 1;
      return respond();
    }),
  );
  return refresh;
}

/** Replace window.location so the reload on a failed refresh is observable. */
function stubReload() {
  const reload = vi.fn();
  vi.stubGlobal("location", { ...window.location, reload });
  return reload;
}

/**
 * A latch that opens once `expected` requests have been answered with 401.
 * Holding the refresh response until it opens makes the concurrent case
 * deterministic: the second 401 is guaranteed to reach the interceptor while a
 * refresh is already in flight, which is the state single-flight is about.
 */
function unauthorizedLatch(expected: number) {
  let seen = 0;
  let open!: () => void;
  const opened = new Promise<void>((resolve) => {
    open = resolve;
  });
  return {
    opened,
    hit() {
      seen += 1;
      if (seen >= expected) open();
    },
  };
}

describe("401 interceptor — endpoints that go through refresh + retry", () => {
  it.each([
    { path: "/auth/me", call: () => client.apiClient.get("/auth/me") },
    { path: "/auth/logout", call: () => client.apiClient.post("/auth/logout") },
    { path: "/projects", call: () => client.apiClient.get("/projects") },
  ])("refreshes and retries a 401 from $path", async ({ path, call }) => {
    server.use(protectedEndpoint(path));
    const refresh = stubRefresh();
    client.setAccessToken(STALE_TOKEN);

    const response = await call();

    expect(response.data).toEqual({ path });
    expect(refresh.calls).toBe(1);
    expect(client.getAccessToken()).toBe(FRESH_TOKEN);
  });

  it.each([
    { path: "/projects/auth/login-notes" },
    { path: "/auth/login-notes" },
    { path: "/oauth/auth/refresh" },
  ])(
    "refreshes and retries a 401 from $path, which only spells a credential endpoint as a substring",
    async ({ path }) => {
      // The rule is stated over endpoints, so it matches whole request paths:
      // a route that merely *contains* /auth/login or /auth/refresh is an
      // ordinary authenticated route and must keep its retry. Matching by
      // substring would silently drop such a route out of the refresh flow —
      // the trap waiting for whoever extends the list with OAuth routes.
      server.use(protectedEndpoint(path));
      const refresh = stubRefresh();
      client.setAccessToken(STALE_TOKEN);

      const response = await client.apiClient.get(path);

      expect(response.data).toEqual({ path });
      expect(refresh.calls).toBe(1);
    },
  );

  it("treats a request with no reported URL as needing a token", async () => {
    // originalRequest.url is optional in axios; an unclassifiable request must
    // fall on the safe side (retried) rather than be silently excluded.
    server.use(protectedEndpoint(""));
    const refresh = stubRefresh();
    client.setAccessToken(STALE_TOKEN);

    const response = await client.apiClient.request({ method: "get" });

    expect(response.status).toBe(200);
    expect(refresh.calls).toBe(1);
  });

  it("serves concurrent 401s with a single refresh", async () => {
    const latch = unauthorizedLatch(2);
    server.use(
      protectedEndpoint("/projects", latch.hit),
      protectedEndpoint("/chats/recent", latch.hit),
    );
    const refresh = stubRefresh(async () => {
      await latch.opened;
      await delay(20); // let the second 401 reach the interceptor
      return HttpResponse.json({ access_token: FRESH_TOKEN });
    });
    client.setAccessToken(STALE_TOKEN);

    const responses = await Promise.all([
      client.apiClient.get("/projects"),
      client.apiClient.get("/chats/recent"),
    ]);

    expect(responses.map((r) => r.data)).toEqual([
      { path: "/projects" },
      { path: "/chats/recent" },
    ]);
    expect(refresh.calls).toBe(1);
  });
});

describe("401 interceptor — endpoints kept out of the refresh flow", () => {
  it.each([
    {
      path: "/auth/login",
      call: () =>
        client.apiClient.post("/auth/login", { name: "u", password: "p" }),
    },
    {
      path: "/auth/register",
      call: () =>
        client.apiClient.post("/auth/register", { name: "u", password: "p" }),
    },
  ])("rejects a 401 from $path without refreshing", async ({ path, call }) => {
    // Bad credentials are not a stale session: refreshing would be pointless
    // and would drop the user out of the app on its failure.
    server.use(
      http.post(`/api${path}`, () =>
        HttpResponse.json({ detail: "no" }, { status: 401 }),
      ),
    );
    const refresh = stubRefresh();
    const reload = stubReload();
    client.setAccessToken(STALE_TOKEN);

    await expect(call()).rejects.toMatchObject({ response: { status: 401 } });

    expect(refresh.calls).toBe(0);
    expect(client.getAccessToken()).toBe(STALE_TOKEN);
    expect(reload).not.toHaveBeenCalled();
  });

  it("does not refresh a 401 that came from /auth/refresh itself", async () => {
    // The recursion guard: /auth/refresh is the request that repairs a stale
    // token, so a 401 from it must surface, not spawn another refresh.
    const refresh = stubRefresh(() => new HttpResponse(null, { status: 401 }));
    const reload = stubReload();
    client.setAccessToken(STALE_TOKEN);

    await expect(client.apiClient.post("/auth/refresh")).rejects.toMatchObject({
      response: { status: 401 },
    });

    expect(refresh.calls).toBe(1); // the direct call, and nothing on top of it
    expect(client.getAccessToken()).toBe(STALE_TOKEN);
    expect(reload).not.toHaveBeenCalled();
  });

  it("passes a non-401 error through untouched", async () => {
    server.use(
      http.get("/api/projects", () => new HttpResponse(null, { status: 500 })),
    );
    const refresh = stubRefresh();
    client.setAccessToken(STALE_TOKEN);

    await expect(client.apiClient.get("/projects")).rejects.toMatchObject({
      response: { status: 500 },
    });

    expect(refresh.calls).toBe(0);
  });
});

describe("401 interceptor — when the retry or the refresh fails", () => {
  it("gives up after one retry instead of looping on a repeated 401", async () => {
    // A server that answers 401 even with a fresh token must not put the client
    // into an endless refresh/retry spin. The endpoint stops answering 401
    // after the second call, so an interceptor without the anti-loop guard
    // terminates too — and fails this case by its assertions (a third request
    // was made, and the call resolved instead of rejecting) rather than by
    // spinning the runner until the job times out.
    const endpoint = { hits: 0 };
    server.use(
      http.get("/api/auth/me", () => {
        endpoint.hits += 1;
        return endpoint.hits > 2
          ? HttpResponse.json({ looped: true })
          : new HttpResponse(null, { status: 401 });
      }),
    );
    const refresh = stubRefresh();
    client.setAccessToken(STALE_TOKEN);

    await expect(client.apiClient.get("/auth/me")).rejects.toMatchObject({
      response: { status: 401 },
    });

    expect(endpoint.hits).toBe(2); // the original request plus exactly one retry
    expect(refresh.calls).toBe(1);
  });

  it("clears the token and reloads the app when the refresh is rejected", async () => {
    server.use(protectedEndpoint("/projects"));
    stubRefresh(() => new HttpResponse(null, { status: 401 }));
    const reload = stubReload();
    client.setAccessToken(STALE_TOKEN);

    // The rejection carries the refresh failure, not some other mishap on the
    // way — that is what tells the caller the session is gone.
    await expect(client.apiClient.get("/projects")).rejects.toMatchObject({
      response: { status: 401 },
    });

    expect(client.getAccessToken()).toBeNull();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("rejects the requests queued behind a failed refresh as well", async () => {
    const latch = unauthorizedLatch(2);
    server.use(
      protectedEndpoint("/projects", latch.hit),
      protectedEndpoint("/chats/recent", latch.hit),
    );
    const refresh = stubRefresh(async () => {
      await latch.opened;
      await delay(20);
      return new HttpResponse(null, { status: 401 });
    });
    stubReload();
    client.setAccessToken(STALE_TOKEN);

    const outcomes = await Promise.allSettled([
      client.apiClient.get("/projects"),
      client.apiClient.get("/chats/recent"),
    ]);

    // Both — the request that started the refresh and the one that queued
    // behind it — are rejected with the refresh failure itself.
    expect(outcomes).toMatchObject([
      { status: "rejected", reason: { response: { status: 401 } } },
      { status: "rejected", reason: { response: { status: 401 } } },
    ]);
    expect(refresh.calls).toBe(1);
    expect(client.getAccessToken()).toBeNull();
  });
});
