import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";

import {
  clearAccessToken,
  ensureFreshToken,
  getAccessToken,
  setAccessToken,
} from "./client";

// Token storage + proactive SSE-token refresh. ensureFreshToken decodes the JWT
// exp and only hits /auth/refresh when the token is near expiry; the refresh
// endpoint is mocked via MSW.

afterEach(() => {
  localStorage.clear();
});

describe("access token storage", () => {
  it("round-trips a token through localStorage", () => {
    expect(getAccessToken()).toBeNull();

    setAccessToken("tok-123");
    expect(getAccessToken()).toBe("tok-123");

    clearAccessToken();
    expect(getAccessToken()).toBeNull();
  });
});

describe("ensureFreshToken", () => {
  it("returns null when there is no token", async () => {
    expect(await ensureFreshToken()).toBeNull();
  });

  it("returns the current token when it is far from expiry, without refreshing", async () => {
    const token = fakeJwt(3600);
    setAccessToken(token);

    expect(await ensureFreshToken()).toBe(token);
  });

  it("clears a malformed token and returns null", async () => {
    setAccessToken("not-a-jwt");

    expect(await ensureFreshToken()).toBeNull();
    expect(getAccessToken()).toBeNull();
  });

  it("refreshes and stores a new token when the current one is near expiry", async () => {
    server.use(
      http.post("/api/auth/refresh", () =>
        HttpResponse.json({ access_token: "refreshed-token" }),
      ),
    );
    setAccessToken(fakeJwt(10)); // expires in ~10s, under the 30s threshold

    const result = await ensureFreshToken();

    expect(result).toBe("refreshed-token");
    expect(getAccessToken()).toBe("refreshed-token");
  });
});
