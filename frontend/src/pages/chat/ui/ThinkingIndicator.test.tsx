import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThinkingIndicator } from "./ThinkingIndicator";

// Unit: мгновенная обратная связь «агент думает» — статусный live-регион,
// который MessageList показывает от отправки сообщения до первого
// рендеримого контента стрима.

describe("ThinkingIndicator", () => {
  it("renders a status region announcing the agent is thinking", () => {
    render(<ThinkingIndicator />);

    expect(
      screen.getByRole("status", { name: "Агент думает" }),
    ).toBeInTheDocument();
  });
});
