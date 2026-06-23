import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/test-utils";

import { SecurityFilter } from "./SecurityFilter";

// Unit: the security event/alert filter bar. Its contract is the FilterState it
// emits through onFilterChange when "Применить"/"Сброс" are pressed. The severity
// Select popup is driven for real under jsdom (pointer-event polyfill).

describe("SecurityFilter", () => {
  it("emits the typed event type on apply", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderWithProviders(<SecurityFilter onFilterChange={onFilterChange} />);

    await user.type(screen.getByLabelText("Тип события"), "auth.x");
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(onFilterChange).toHaveBeenCalledWith({ event_type: "auth.x" });
  });

  it("emits the chosen severity selected from the open listbox", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderWithProviders(<SecurityFilter onFilterChange={onFilterChange} />);

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Критично" }));
    await user.click(screen.getByRole("button", { name: "Применить" }));

    expect(onFilterChange).toHaveBeenCalledWith({ severity: "critical" });
  });

  it("clears all filters on reset", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    renderWithProviders(<SecurityFilter onFilterChange={onFilterChange} />);

    await user.type(screen.getByLabelText("Тип события"), "auth.x");
    await user.click(screen.getByRole("button", { name: "Сброс" }));

    expect(onFilterChange).toHaveBeenLastCalledWith({});
  });
});
