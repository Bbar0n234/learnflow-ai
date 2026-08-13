import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ArtifactCard } from "./ArtifactCard";

// Integration: the chat-feed artifact card (`ArtifactPart`, ADR-032; T2.5).
// Identity is the path (query-addressed, not UUID) — no more `message.artifacts`.
// For an image extension it shows a 64x40 preview pulled from the media
// endpoint (same query key as the viewer, now path-addressed too); other
// extensions keep the plain FileText icon and issue no media request.
// Errors/404 fall back to an icon, never a broken <img>. The card links to
// `?path=`, and `kind: "updated"` shows a badge with its line delta (or no
// counters when `diff` is null for a binary rewrite).

const MEDIA_URL = "/api/projects/p1/artifacts/media";
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

interface CardArtifact {
  path: string;
  title: string;
  artifactType: string;
  kind: "created" | "updated";
  diff: { added: number; removed: number } | null;
}

function artifact(overrides: Partial<CardArtifact> = {}): CardArtifact {
  return {
    path: "cover.png",
    title: "Cover",
    artifactType: "png",
    kind: "created",
    diff: null,
    ...overrides,
  };
}

function renderCard(item: CardArtifact) {
  const ui: ReactElement = (
    <MemoryRouter>
      <ArtifactCard artifact={item} projectId="p1" />
    </MemoryRouter>
  );
  return renderWithProviders(ui);
}

describe("ArtifactCard", () => {
  it("renders a media preview for an image extension", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { container } = renderCard(artifact());

    // Decorative thumbnail (alt="", aria-hidden) — no accessible role, so we
    // assert the rendered <img> and its objectURL src directly.
    await waitFor(() => expect(container.querySelector("img")).not.toBeNull());
    expect(container.querySelector("img")).toHaveAttribute(
      "src",
      "blob:mock/thumb",
    );
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });

  it("links to the viewer by path, including nested ones", () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    renderCard(artifact({ path: "lecture-1/cover.png" }));

    expect(screen.getByRole("link", { name: /Cover/ })).toHaveAttribute(
      "href",
      "/projects/p1/artifacts?path=lecture-1%2Fcover.png",
    );
  });

  it("shows the path under the title", () => {
    renderCard(
      artifact({
        path: "lecture-1/konspekt.md",
        title: "konspekt.md",
        artifactType: "md",
      }),
    );

    expect(screen.getByText("lecture-1/konspekt.md")).toBeInTheDocument();
  });

  it("shows the plain icon and issues no media request for a non-image extension", () => {
    // No media handler registered: a request would trip MSW onUnhandledRequest.
    const { container } = renderCard(
      artifact({ artifactType: "md", title: "Notes" }),
    );

    expect(container.querySelector("img")).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(screen.getByText("Notes")).toBeInTheDocument();
  });

  it("falls back to an icon (no broken img) when the media is missing", async () => {
    server.use(
      http.get(MEDIA_URL, () =>
        HttpResponse.json({ detail: "no blob" }, { status: 404 }),
      ),
    );

    const { container } = renderCard(artifact());

    // Error state settles: an icon (svg), never an <img>, and no objectURL.
    await waitFor(() => expect(container.querySelector("svg")).not.toBeNull());
    expect(container.querySelector("img")).toBeNull();
    expect(createObjectURL).not.toHaveBeenCalled();
    // Card stays clickable — the viewer differentiates 404 vs error there.
    expect(screen.getByRole("link", { name: /Cover/ })).toBeInTheDocument();
  });

  it("revokes the thumbnail objectURL on unmount", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { container, unmount } = renderCard(artifact());
    await waitFor(() => expect(container.querySelector("img")).not.toBeNull());

    unmount();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock/thumb");
  });

  it("shows no badge for a freshly created artifact", () => {
    renderCard(artifact({ kind: "created", artifactType: "md" }));

    expect(screen.queryByText(/обновлён/)).not.toBeInTheDocument();
  });

  it("shows the updated badge with its line delta", () => {
    renderCard(
      artifact({
        kind: "updated",
        diff: { added: 12, removed: 3 },
        artifactType: "md",
      }),
    );

    expect(screen.getByText("обновлён · +12 −3")).toBeInTheDocument();
  });

  it("shows the updated badge without counters for a binary rewrite (diff: null)", () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    renderCard(artifact({ kind: "updated", diff: null, artifactType: "png" }));

    expect(screen.getByText("обновлён")).toBeInTheDocument();
  });
});
