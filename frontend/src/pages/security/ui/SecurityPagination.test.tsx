import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/test-utils";

import { SecurityPagination } from "./SecurityPagination";

// Unit: the security list pager. It renders the current page summary and emits
// offset/limit changes through callbacks. The prev/next controls are icon-only
// buttons, so their accessible name is the only thing a screen reader has to go
// on — in a Russian product it is Russian too (design-brief блок 2 «Заодно»).

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

    const prev = screen.getByRole("button", { name: "Предыдущая страница" });
    const next = screen.getByRole("button", { name: "Следующая страница" });
    expect(prev).toBeDisabled();
    expect(next).toBeEnabled();

    await user.click(next);
    expect(onOffsetChange).toHaveBeenCalledWith(50);
  });

  it("goes back a page from a middle offset", async () => {
    const user = userEvent.setup();
    const { onOffsetChange } = setup({ offset: 50 });

    const prev = screen.getByRole("button", { name: "Предыдущая страница" });
    expect(prev).toBeEnabled();

    await user.click(prev);
    expect(onOffsetChange).toHaveBeenCalledWith(0);
  });

  it("disables next on the last page", () => {
    setup({ offset: 100 });

    const next = screen.getByRole("button", { name: "Следующая страница" });
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
