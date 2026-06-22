import { describe, expect, it } from "vitest";

import { cn } from "./utils";

// Unit: cn = clsx + tailwind-merge. Joins, drops falsy, and lets a later
// Tailwind utility win over an earlier conflicting one.
describe("cn", () => {
  it("joins truthy class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("drops falsy and conditional entries", () => {
    expect(cn("a", false, null, undefined, "", "b")).toBe("a b");
  });

  it("lets the last conflicting Tailwind utility win", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("keeps non-conflicting Tailwind utilities", () => {
    expect(cn("px-2", "py-4")).toBe("px-2 py-4");
  });
});
