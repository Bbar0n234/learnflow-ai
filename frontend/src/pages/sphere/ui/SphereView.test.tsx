import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { SphereView } from "./SphereView";

// Integration: the knowledge-sphere page. Fetches /projects/:id/sphere, renders
// the markdown viewer, switches to the editor, and persists edits via PUT —
// returning to the viewer with the invalidated query refetched.

const SPHERE_URL = "/api/projects/p1/sphere";

/**
 * Кнопка «Редактировать» стоит в двух местах сразу — в шапке вьюера и при
 * подсказке пустой сферы, — поэтому по одному доступному имени они
 * неразличимы. Идём от самой подсказки вверх до ближайшего предка, внутри
 * которого такая кнопка есть: запрос остаётся про поведение («действие при
 * подсказке»), а не про вёрстку блока.
 */
function editActionNextTo(hint: HTMLElement): HTMLElement {
  for (let block = hint.parentElement; block; block = block.parentElement) {
    const actions = within(block).queryAllByRole("button", {
      name: "Редактировать",
    });
    if (actions.length === 0) continue;
    // `queryAllBy*`, а не `queryBy*`: если вёрстка когда-нибудь сведёт обе
    // одноимённые кнопки под общего предка, падение должно называть причину,
    // а не приходить как «found multiple elements» из недр запроса.
    expect(
      actions,
      "Рядом с подсказкой пустой сферы ожидалась ровно одна кнопка «Редактировать»; " +
        "нашлось несколько — подсказка и шапка вьюера съехали под общего предка",
    ).toHaveLength(1);
    // Единственность только что утверждена — индекс безопасен.
    return actions[0]!;
  }
  throw new Error("Действие «Редактировать» не найдено рядом с подсказкой");
}

function render() {
  return renderWithProviders(
    routerAt(<SphereView />, {
      path: "/projects/:id/sphere",
      entry: "/projects/p1/sphere",
    }),
  );
}

describe("SphereView", () => {
  it("names what is loading while the sphere is in flight", async () => {
    server.use(
      http.get(SPHERE_URL, async () => {
        await delay(50);
        return HttpResponse.json({
          project_id: "p1",
          content: "# Course goals",
          updated_at: "2026-02-01T00:00:00Z",
        });
      }),
    );

    render();

    // Панельная загрузка называет, что грузится, по-русски (блоки 3 и 2
    // «Заодно») — та же форма, что несёт соседняя панель артефакта.
    expect(screen.getByText("Загрузка сферы…")).toBeInTheDocument();

    await screen.findByText("Course goals");
  });

  it("renders the sphere content from the API", async () => {
    server.use(
      http.get(SPHERE_URL, () =>
        HttpResponse.json({
          project_id: "p1",
          content: "# Course goals",
          updated_at: "2026-02-01T00:00:00Z",
        }),
      ),
    );

    render();

    expect(await screen.findByText("Course goals")).toBeInTheDocument();
  });

  it("shows the empty hint when the sphere has no content", async () => {
    server.use(
      http.get(SPHERE_URL, () =>
        HttpResponse.json({
          project_id: "p1",
          content: "",
          updated_at: "2026-02-01T00:00:00Z",
        }),
      ),
    );

    render();

    expect(await screen.findByText(/Сфера знаний пуста/)).toBeInTheDocument();
  });

  it("offers the editor right from the empty sphere", async () => {
    server.use(
      http.get(SPHERE_URL, () =>
        HttpResponse.json({
          project_id: "p1",
          content: "",
          updated_at: "2026-02-01T00:00:00Z",
        }),
      ),
    );
    const user = userEvent.setup();

    render();

    // Подсказка пустой сферы несёт собственное действие (блок 6.1 брифа) —
    // берём кнопку, стоящую при подсказке, а не ту, что живёт в шапке вьюера.
    const hint = await screen.findByText(/Сфера знаний пуста/);
    await user.click(editActionNextTo(hint));

    expect(
      await screen.findByLabelText("Содержимое сферы знаний"),
    ).toBeInTheDocument();
  });

  it("shows an error state when the sphere fails to load", async () => {
    server.use(
      http.get(SPHERE_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    render();

    expect(
      await screen.findByRole("heading", {
        name: "Не удалось загрузить сферу знаний",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Проверьте соединение и попробуйте ещё раз/),
    ).toBeInTheDocument();
  });

  it("recovers the sphere from a failure through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(SPHERE_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return HttpResponse.json({
          project_id: "p1",
          content: "# Course goals",
          updated_at: "2026-02-01T00:00:00Z",
        });
      }),
    );
    const user = userEvent.setup();

    render();

    await screen.findByRole("heading", {
      name: "Не удалось загрузить сферу знаний",
    });
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(await screen.findByText("Course goals")).toBeInTheDocument();
  });

  it("edits and saves the sphere, then returns to the viewer with new content", async () => {
    let content = "original";
    server.use(
      http.get(SPHERE_URL, () =>
        HttpResponse.json({
          project_id: "p1",
          content,
          updated_at: "2026-02-01T00:00:00Z",
        }),
      ),
      http.put(SPHERE_URL, async ({ request }) => {
        const body = (await request.json()) as { content: string };
        content = body.content;
        return HttpResponse.json({
          project_id: "p1",
          content,
          updated_at: "2026-02-02T00:00:00Z",
        });
      }),
    );
    const user = userEvent.setup();

    render();
    await screen.findByText("original");

    // The edit (pencil) icon button in the viewer header, by accessible name.
    await user.click(screen.getByRole("button", { name: "Редактировать" }));

    const textarea = await screen.findByLabelText("Содержимое сферы знаний");
    await user.clear(textarea);
    await user.type(textarea, "updated body");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() =>
      expect(screen.getByText("updated body")).toBeInTheDocument(),
    );
  });
});
