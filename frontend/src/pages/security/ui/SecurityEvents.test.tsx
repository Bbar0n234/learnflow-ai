import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { SecurityEvent } from "@/shared/api/security";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { SecurityEvents } from "./SecurityEvents";

// Integration: the SIEM security-events tab. Fetches /security/events from the
// SIEM API, renders the table (type, severity badge), surfaces loading / empty /
// error states, and opens a detail modal per row. Network is MSW.

const EVENTS_URL = "/siem/api/security/events";

function event(over: Partial<SecurityEvent> = {}): SecurityEvent {
  return {
    id: 1,
    event_id: "11111111-1111-1111-1111-111111111111",
    event_type: "auth.login.failed",
    severity: "critical",
    event_timestamp: "2026-06-01T10:00:00Z",
    ingested_at: "2026-06-01T10:00:01Z",
    identifiers: { ip: "10.0.0.1" },
    metadata: { attempts: 5 },
    ...over,
  };
}

function page(items: SecurityEvent[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 50,
    offset: 0,
  });
}

describe("SecurityEvents", () => {
  it("holds the table with placeholder rows while events are in flight", async () => {
    server.use(
      http.get(EVENTS_URL, async () => {
        await delay(50);
        return page([]);
      }),
    );

    const { container } = renderWithProviders(<SecurityEvents />);

    // Плашки скелетона не имеют доступного имени — берём публичный маркер
    // примитива дизайн-системы (`data-slot="skeleton"`), последнюю ступень
    // лестницы запросов из testing.md § Frontend. Число строк, ширины плашек
    // и мерцание jsdom не исполняет: их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    // Пока данные в пути, «событий нет» не объявляется.
    expect(screen.queryByText("События не найдены")).not.toBeInTheDocument();

    await screen.findByText("События не найдены");
  });

  it("shows an empty-state message when there are no events", async () => {
    server.use(http.get(EVENTS_URL, () => page([])));

    renderWithProviders(<SecurityEvents />);

    expect(await screen.findByText("События не найдены")).toBeInTheDocument();
  });

  it("renders an error state when the request fails", async () => {
    server.use(
      http.get(EVENTS_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderWithProviders(<SecurityEvents />);

    // Формулировка канонизирована блоком 4 брифа («Не удалось загрузить …»),
    // детали ответа сохранены рядом с ней.
    expect(
      await screen.findByText(/Не удалось загрузить события: boom/),
    ).toBeInTheDocument();
  });

  it("recovers the events table through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(EVENTS_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return page([event()]);
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SecurityEvents />);

    await screen.findByText(/Не удалось загрузить события/);
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("auth.login.failed")).toBeInTheDocument();
    expect(
      screen.queryByText(/Не удалось загрузить события/),
    ).not.toBeInTheDocument();
  });

  it("lists events with their type and severity", async () => {
    server.use(http.get(EVENTS_URL, () => page([event()])));

    renderWithProviders(<SecurityEvents />);

    expect(await screen.findByText("auth.login.failed")).toBeInTheDocument();
    // SeverityBadge renders the Russian severity label.
    expect(screen.getByText("Критично")).toBeInTheDocument();
  });

  it("opens a detail modal exposing the event id", async () => {
    server.use(http.get(EVENTS_URL, () => page([event()])));
    const user = userEvent.setup();

    renderWithProviders(<SecurityEvents />);
    await screen.findByText("auth.login.failed");

    await user.click(screen.getByRole("button", { name: "Детали" }));

    expect(await screen.findByText("Детали события")).toBeInTheDocument();
    expect(
      screen.getByText("11111111-1111-1111-1111-111111111111"),
    ).toBeInTheDocument();
  });
});
