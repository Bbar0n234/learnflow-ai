import { describe, expect, it } from "vitest";

import { useUIStore } from "./ui-store";

// Unit: sidebar visibility toggle. Store auto-resets between tests.
describe("ui-store", () => {
  it("starts with the sidebar open", () => {
    expect(useUIStore.getState().sidebarOpen).toBe(true);
  });

  it("flips sidebar visibility on each toggle", () => {
    const { toggleSidebar } = useUIStore.getState();

    toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(false);

    toggleSidebar();
    expect(useUIStore.getState().sidebarOpen).toBe(true);
  });
});
