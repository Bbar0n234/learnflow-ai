import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { ArtifactView } from "./ArtifactView";

// Integration (feat-013, трек T4): панель артефакта в переходных состояниях.
// Загрузка и ошибка здесь — «панельная» половина блоков 3 и 4 брифа: спиннер с
// русской подписью вместо голой строки и полноэкранная карточка ошибки, из
// которой есть выход помимо F5. Форма общая с чатом и сферой — разнобой между
// панелями и был тем, против чего заведён блок 2. Сеть — MSW; компонент читает
// :id/:aid из маршрута, поэтому монтируется в роутере.

const ARTIFACT_URL = "/api/projects/p1/artifacts/a1";

function artifactResponse() {
  return HttpResponse.json({
    id: "a1",
    title: "Конспект лекции",
    type: "summary",
    content: "Тело конспекта",
    thread_id: null,
    message_id: null,
    created_at: "2026-02-01T12:00:00Z",
  });
}

function render() {
  return renderWithProviders(
    routerAt(<ArtifactView />, {
      path: "/projects/:id/artifacts/:aid",
      entry: "/projects/p1/artifacts/a1",
    }),
  );
}

describe("ArtifactView", () => {
  it("names what is loading while the artifact is in flight", async () => {
    server.use(
      http.get(ARTIFACT_URL, async () => {
        await delay(50);
        return artifactResponse();
      }),
    );

    render();

    expect(screen.getByText("Загрузка артефакта…")).toBeInTheDocument();

    await screen.findByRole("heading", { name: "Конспект лекции" });
  });

  it("explains a failed load and offers a way out of it", async () => {
    server.use(
      http.get(ARTIFACT_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render();

    expect(
      await screen.findByRole("heading", {
        name: "Не удалось загрузить артефакт",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Проверьте соединение и попробуйте ещё раз/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Повторить" }),
    ).toBeInTheDocument();
  });

  it("recovers the artifact through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(ARTIFACT_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return artifactResponse();
      }),
    );
    const user = userEvent.setup();

    render();

    await screen.findByRole("heading", {
      name: "Не удалось загрузить артефакт",
    });
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("heading", { name: "Конспект лекции" }),
    ).toBeInTheDocument();
  });
});
