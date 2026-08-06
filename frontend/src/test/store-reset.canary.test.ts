import { describe, expect, it } from "vitest";

import { useUIStore } from "@/stores/ui-store";

// Canary for the Zustand auto-reset guard (frontend/__mocks__/zustand.ts +
// vi.mock("zustand") in setup.ts). Module-level stores leak state between tests
// unless reset in afterEach. The first test mutates the store; the second proves
// it was rolled back to initial state. If the reset wiring regresses, the second
// test fails — leakage is caught green before the freeze.
describe("zustand store reset guard", () => {
  it("mutates the ui store away from its initial state", () => {
    expect(useUIStore.getState().sidebarOpen).toBe(true);

    useUIStore.getState().toggleSidebar();

    expect(useUIStore.getState().sidebarOpen).toBe(false);
  });

  it("sees the store back at its initial state in the next test", () => {
    expect(useUIStore.getState().sidebarOpen).toBe(true);
  });
});
