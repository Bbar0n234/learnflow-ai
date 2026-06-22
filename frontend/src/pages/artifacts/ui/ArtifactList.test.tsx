import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import { routerAt } from "@/test/router";

import { ArtifactList } from "./ArtifactList";

// Integration: the project artifacts list. Reads :id from the route, fetches
// /projects/:id/artifacts, and renders loading / error / empty / populated
// states. Each artifact is a Link, so the page must be mounted in a router.

const ARTIFACTS_URL = "/api/projects/p1/artifacts";

function render() {
  return renderWithProviders(
    routerAt(<ArtifactList />, {
      path: "/projects/:id/artifacts",
      entry: "/projects/p1/artifacts",
    }),
  );
}

describe("ArtifactList", () => {
  it("lists artifacts returned by the API", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({
          items: [
            {
              id: "a1",
              title: "Lecture notes",
              type: "summary",
              created_at: "2026-02-01T12:00:00Z",
            },
            {
              id: "a2",
              title: "Flashcards",
              type: "cards",
              created_at: "2026-02-02T12:00:00Z",
            },
          ],
          total: 2,
          limit: 200,
          offset: 0,
        }),
      ),
    );

    render();

    expect(await screen.findByText("Lecture notes")).toBeInTheDocument();
    expect(screen.getByText("Flashcards")).toBeInTheDocument();
    // Each artifact links to its detail route.
    expect(screen.getByRole("link", { name: /Lecture notes/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts/a1",
    );
  });

  it("shows the empty state when there are no artifacts", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 }),
      ),
    );

    render();

    expect(await screen.findByText(/No artifacts yet/)).toBeInTheDocument();
  });

  it("shows an error message when the request fails", async () => {
    server.use(
      http.get(ARTIFACTS_URL, () =>
        HttpResponse.json({ detail: "nope" }, { status: 500 }),
      ),
    );

    render();

    expect(
      await screen.findByText("Failed to load artifacts."),
    ).toBeInTheDocument();
  });
});
