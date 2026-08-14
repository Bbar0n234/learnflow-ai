import "@/test/pointer-event-polyfill";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { SecurityAlerts } from "./SecurityAlerts";

// Integration (feat-013, трек T4): вкладка алертов SIEM в переходных
// состояниях. Три вкладки одного экрана — события, алерты, правила — обязаны
// вести себя одинаково (блоки 3 и 4 брифа), поэтому алерты проверяются тем же
// набором, что и события: плейсхолдеры вместо плоской строки загрузки и
// карточка ошибки, из которой есть выход помимо F5. Сеть — MSW.

const ALERTS_URL = "/siem/api/security/alerts";

function emptyPage() {
  return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
}

describe("SecurityAlerts", () => {
  it("holds the table with placeholder rows while alerts are in flight", async () => {
    server.use(
      http.get(ALERTS_URL, async () => {
        await delay(50);
        return emptyPage();
      }),
    );

    const { container } = renderWithProviders(<SecurityAlerts />);

    // Плашки скелетона не имеют доступного имени — берём публичный маркер
    // примитива дизайн-системы (`data-slot="skeleton"`), последнюю ступень
    // лестницы запросов из testing.md § Frontend. Число строк, ширины плашек
    // и мерцание jsdom не исполняет: их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    // Пока данные в пути, «алертов нет» не объявляется.
    expect(screen.queryByText("Алерты не найдены")).not.toBeInTheDocument();

    await screen.findByText("Алерты не найдены");
  });

  it("recovers the alerts table through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(ALERTS_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return emptyPage();
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<SecurityAlerts />);

    // Формулировка канонизирована блоком 4 брифа, детали ответа сохранены.
    expect(
      await screen.findByText(/Не удалось загрузить алерты: boom/),
    ).toBeInTheDocument();
    failing = false;
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Алерты не найдены")).toBeInTheDocument();
    expect(
      screen.queryByText(/Не удалось загрузить алерты/),
    ).not.toBeInTheDocument();
  });
});
