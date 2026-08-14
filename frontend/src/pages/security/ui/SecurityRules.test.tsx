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
  it("holds the table with placeholder rows while rules are in flight", async () => {
    server.use(
      http.get(RULES_URL, async () => {
        await delay(50);
        return page([]);
      }),
    );

    const { container } = renderWithProviders(<SecurityRules />);

    // Плашки скелетона не имеют доступного имени — берём публичный маркер
    // примитива дизайн-системы (`data-slot="skeleton"`), последнюю ступень
    // лестницы запросов из testing.md § Frontend. Число строк, ширины плашек
    // и мерцание jsdom не исполняет: их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    // Пока данные в пути, «правил нет» не объявляется.
    expect(screen.queryByText("Правила не найдены")).not.toBeInTheDocument();

    await screen.findByText("Правила не найдены");
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

    // Формулировка канонизирована блоком 4 брифа («Не удалось загрузить …»),
    // детали ответа сохранены рядом с ней.
    expect(
      await screen.findByText(/Не удалось загрузить правила: boom/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Повторить" }),
    ).toBeInTheDocument();
  });

  it("recovers the rules table through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(RULES_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return page([rule()]);
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SecurityRules />);

    await screen.findByText(/Не удалось загрузить правила/);
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    // Проводка `onRetry → refetch` у каждой вкладки своя, поэтому проверяется
    // отдельно — иначе сломанное «Повторить» именно здесь никто бы не поймал.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("brute_force_auth")).toBeInTheDocument();
    expect(
      screen.queryByText(/Не удалось загрузить правила/),
    ).not.toBeInTheDocument();
  });

  it("lists a configured rule with its type", async () => {
    server.use(http.get(RULES_URL, () => page([rule()])));

    renderWithProviders(<SecurityRules />);

    expect(await screen.findByText("brute_force_auth")).toBeInTheDocument();
    expect(screen.getByText("Порог")).toBeInTheDocument();
  });

  it("names the row actions in Russian for a screen reader", async () => {
    server.use(http.get(RULES_URL, () => page([rule()])));

    renderWithProviders(<SecurityRules />);
    const row = (await screen.findByText("brute_force_auth")).closest("tr")!;

    // Кнопки строки — иконки без подписи, их единственное имя для скринридера
    // задаётся `aria-label`; в русском продукте оно русское (бриф блок 2).
    expect(
      within(row).getByRole("button", { name: "Редактировать правило" }),
    ).toBeInTheDocument();
    expect(
      within(row).getByRole("button", { name: "Удалить правило" }),
    ).toBeInTheDocument();
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

    // The row holds two icon-only buttons reached by accessible name.
    await user.click(
      within(row).getByRole("button", { name: "Удалить правило" }),
    );

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
    // window (60) and threshold (5) are prefilled. Fields are reached by their
    // associated labels.
    await user.type(screen.getByLabelText("Название"), "new_rule");
    await user.type(
      screen.getByLabelText("Шаблон типа события"),
      "auth.login.failed",
    );
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Правило создано")).toBeInTheDocument();
    expect(await screen.findByText("new_rule")).toBeInTheDocument();
  });
});
