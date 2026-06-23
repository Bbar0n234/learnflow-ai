import "@/test/pointer-event-polyfill";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { CorrelationRule } from "@/shared/api/security";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { SecurityRules } from "./SecurityRules";

// Integration: the SIEM correlation-rules tab. Lists rules from the SIEM API and
// drives the create / delete mutations, each followed by a refetch that updates
// the table. Loading / empty / error states are covered too. Network is MSW.

const RULES_URL = "/siem/api/security/rules";

function rule(over: Partial<CorrelationRule> = {}): CorrelationRule {
  return {
    id: 1,
    name: "brute_force_auth",
    description: "Detects repeated auth failures",
    rule_type: "threshold",
    enabled: true,
    config: { window: 60, threshold: 5 },
    created_at: "2026-06-01T10:00:00Z",
    updated_at: "2026-06-01T10:00:00Z",
    ...over,
  };
}

function page(items: CorrelationRule[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 50,
    offset: 0,
  });
}

describe("SecurityRules", () => {
  it("shows a loading hint while rules are in flight", () => {
    server.use(
      http.get(RULES_URL, async () => {
        await delay(50);
        return page([]);
      }),
    );

    renderWithProviders(<SecurityRules />);

    expect(screen.getByText("Загрузка правил...")).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no rules", async () => {
    server.use(http.get(RULES_URL, () => page([])));

    renderWithProviders(<SecurityRules />);

    expect(await screen.findByText("Правила не найдены")).toBeInTheDocument();
  });

  it("renders an error state when the request fails", async () => {
    server.use(
      http.get(RULES_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(<SecurityRules />);

    expect(
      await screen.findByText(/Ошибка загрузки правил/),
    ).toBeInTheDocument();
  });

  it("lists a configured rule with its type", async () => {
    server.use(http.get(RULES_URL, () => page([rule()])));

    renderWithProviders(<SecurityRules />);

    expect(await screen.findByText("brute_force_auth")).toBeInTheDocument();
    expect(screen.getByText("Порог")).toBeInTheDocument();
  });

  it("deletes a rule after confirmation and refetches", async () => {
    let deleted = false;
    server.use(
      http.get(RULES_URL, () => page(deleted ? [] : [rule()])),
      http.delete(`${RULES_URL}/1`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SecurityRules />);
    const row = (await screen.findByText("brute_force_auth")).closest("tr")!;

    // The row holds two icon-only buttons (edit, delete); delete is the second.
    const buttons = within(row).getAllByRole("button");
    await user.click(buttons[buttons.length - 1]!);

    // Confirm in the modal.
    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    expect(await screen.findByText("Правило удалено")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("Правила не найдены")).toBeInTheDocument(),
    );
  });

  it("creates a rule through the form and shows it after the refetch", async () => {
    let created = false;
    server.use(
      http.get(RULES_URL, () =>
        page(created ? [rule({ id: 2, name: "new_rule" })] : []),
      ),
      http.post(RULES_URL, async () => {
        created = true;
        return HttpResponse.json(rule({ id: 2, name: "new_rule" }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SecurityRules />);
    await screen.findByText("Правила не найдены");

    await user.click(screen.getByRole("button", { name: /Создать правило/ }));

    // Threshold rule (the form default) needs a name and an event-type pattern;
    // window (60) and threshold (5) are prefilled. Labels are not associated with
    // inputs (a11y gap, see run-log), so fields are reached by placeholder.
    await user.type(
      screen.getByPlaceholderText("brute_force_auth"),
      "new_rule",
    );
    await user.type(
      screen.getByPlaceholderText(/auth\.login\.failed/),
      "auth.login.failed",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Правило создано")).toBeInTheDocument();
    expect(await screen.findByText("new_rule")).toBeInTheDocument();
  });
});
