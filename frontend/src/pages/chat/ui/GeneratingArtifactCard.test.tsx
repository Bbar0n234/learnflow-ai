import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GeneratingArtifactCard } from "./GeneratingArtifactCard";

// Unit: the generation placeholder (feat-010, T2.4). A static presentational
// card — announces itself as a live status region and shows the fixed label.

describe("GeneratingArtifactCard", () => {
  it("renders a status region with the generating label", () => {
    render(<GeneratingArtifactCard />);

    expect(
      screen.getByRole("status", { name: "Идёт генерация изображения" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Генерирую изображение…")).toBeInTheDocument();
  });
});
