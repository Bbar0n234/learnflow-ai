import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ArtifactCard } from "./ArtifactCard";

// Integration: the chat-feed artifact card (feat-010, T2.3). For type "image"
// it shows a 64x40 preview pulled from the media endpoint (same query key as
// the viewer); other types keep the plain FileText icon and issue no media
// request. Errors/404 fall back to an icon, never a broken <img>. The card is
// always a Link to the artifact detail route.

const MEDIA_URL = "/api/projects/p1/artifacts/a1/media";
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

const createObjectURL = vi.fn(() => "blob:mock/thumb");
const revokeObjectURL = vi.fn();

beforeEach(() => {
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  URL.createObjectURL = createObjectURL;
  URL.revokeObjectURL = revokeObjectURL;
});

function pngResponse() {
  return new HttpResponse(PNG_BYTES, {
    headers: { "Content-Type": "image/png" },
  });
}

function renderCard(artifact: { id: string; title: string; type: string }) {
  const ui: ReactElement = (
    <MemoryRouter>
      <ArtifactCard artifact={artifact} projectId="p1" />
    </MemoryRouter>
  );
  return renderWithProviders(ui);
}

describe("ArtifactCard", () => {
  it("renders a media preview for an image artifact", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { container } = renderCard({
      id: "a1",
      title: "Cover",
      type: "image",
    });

    // Decorative thumbnail (alt="", aria-hidden) — no accessible role, so we
    // assert the rendered <img> and its objectURL src directly.
    await waitFor(() => expect(container.querySelector("img")).not.toBeNull());
    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "blob:mock/thumb",
    );
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });

  it("links to the artifact detail route", () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    renderCard({ id: "a1", title: "Cover", type: "image" });

    expect(screen.getByRole("link", { name: /Cover/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts/a1",
    );
  });

  it("shows the plain icon and issues no media request for a non-image type", () => {
    // No media handler registered: a request would trip MSW onUnhandledRequest.
    const { container } = renderCard({
      id: "a1",
      title: "Notes",
      type: "summary",
    });

    expect(container.querySelector("img")).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.getByText("summary")).toBeInTheDocument();
  });

  it("falls back to an icon (no broken img) when the media is missing", async () => {
    server.use(
      http.get(MEDIA_URL, () =>
        HttpResponse.json({ detail: "no blob" }, { status: 404 }),
      ),
    );

    const { container } = renderCard({
      id: "a1",
      title: "Cover",
      type: "image",
    });

    // Error state settles: an icon (svg), never an <img>, and no objectURL.
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelector("img")).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
    // Card stays clickable — the viewer differentiates 404 vs error there.
    expect(screen.getByRole("link", { name: /Cover/ })).toBeInTheDocument();
  });

  it("revokes the thumbnail objectURL on unmount", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { container, unmount } = renderCard({
      id: "a1",
      title: "Cover",
      type: "image",
    });
    await waitFor(() => expect(container.querySelector("img")).not.toBeNull());

    unmount();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock/thumb");
  });
});
