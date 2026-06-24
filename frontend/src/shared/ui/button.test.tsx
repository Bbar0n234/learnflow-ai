import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Button } from "./button";

// Canary: RTL renders a real shared component and queries it by role — proves
// the jsdom + Testing Library harness works. Not coverage.
describe("Button", () => {
  it("renders its label as an accessible button", () => {
    render(<Button>Save changes</Button>);

    expect(
      screen.getByRole("button", { name: "Save changes" }),
    ).toBeInTheDocument();
  });
});
