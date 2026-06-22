import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { SphereView } from "./SphereView";

// Integration: the knowledge-sphere page. Fetches /projects/:id/sphere, renders
// the markdown viewer, switches to the editor, and persists edits via PUT —
// returning to the viewer with the invalidated query refetched.

const SPHERE_URL = "/api/projects/p1/sphere";

function render() {
  return renderWithProviders(
    routerAt(<SphereView />, {
      path: "/projects/:id/sphere",
      entry: "/projects/p1/sphere",
    }),
  );
}

describe("SphereView", () => {
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

    expect(
      await screen.findByText(/Knowledge sphere is empty/),
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
      await screen.findByText("Failed to load sphere."),
    ).toBeInTheDocument();
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

    // Only one button in the viewer header: the edit (pencil) icon button.
    await user.click(screen.getByRole("button"));

    const textarea = await screen.findByPlaceholderText(
      /Write your knowledge sphere content/,
    );
    await user.clear(textarea);
    await user.type(textarea, "updated body");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(screen.getByText("updated body")).toBeInTheDocument(),
    );
  });
});
