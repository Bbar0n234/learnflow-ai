import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/test-utils";

import { SecurityPagination } from "./SecurityPagination";

// Unit: the security list pager. It renders the current page summary and emits
// offset/limit changes through callbacks. The prev/next controls are icon-only
// buttons without accessible names (a11y gap, see run-log); they are
// distinguished here by their disabled state at the page boundaries.

function setup(over: Partial<Parameters<typeof SecurityPagination>[0]> = {}) {
  const onLimitChange = vi.fn();
  const onOffsetChange = vi.fn();
  renderWithProviders(
    <SecurityPagination
      limit={50}
      offset={0}
      total={120}
      onLimitChange={onLimitChange}
      onOffsetChange={onOffsetChange}
      {...over}
    />,
  );
  return { onLimitChange, onOffsetChange };
}

describe("SecurityPagination", () => {
  it("shows the current page summary", () => {
    setup();

    expect(screen.getByText("Страница 1 из 3 (всего 120)")).toBeInTheDocument();
  });

  it("disables previous on the first page and advances on next", async () => {
    const user = userEvent.setup();
    const { onOffsetChange } = setup();

    const buttons = screen.getAllByRole("button");
    const prev = buttons[0]!;
    const next = buttons[1]!;
    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();

    await user.click(next);
    expect(onOffsetChange).toHaveBeenCalledWith(50);
  });

  it("goes back a page from a middle offset", async () => {
    const user = userEvent.setup();
    const { onOffsetChange } = setup({ offset: 50 });

    const prev = screen.getAllByRole("button")[0]!;
    expect(prev).toBeEnabled();

    await user.click(prev);
    expect(onOffsetChange).toHaveBeenCalledWith(0);
  });

  it("disables next on the last page", () => {
    setup({ offset: 100 });

    const next = screen.getAllByRole("button")[1]!;
    expect(next).toBeDisabled();
  });

  it("emits the page size chosen from the open listbox", async () => {
    const user = userEvent.setup();
    const { onLimitChange } = setup();

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "25" }));

    expect(onLimitChange).toHaveBeenCalledWith(25);
  });
});
