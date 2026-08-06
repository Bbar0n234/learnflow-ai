import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { server } from "./msw/server";

// Route Zustand stores through the auto-mock (__mocks__/zustand.ts) so
// module-level store state resets between tests instead of leaking.
vi.mock("zustand");

// MSW intercepts network at the request layer; unhandled requests fail loudly.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));

afterEach(() => {
  server.resetHandlers();
  cleanup();
});

afterAll(() => server.close());
