import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ImageViewer } from "./ImageViewer";

// Integration: the live image viewer (feat-010, T2.2). Fetches the media blob
// via useArtifactMedia, turns it into an objectURL, and drives three visual
// states — loading (shimmer) / ready (img + download + zoom) / empty (404 or
// error). Network via MSW; objectURL create/revoke are stubbed (jsdom has no
// URL.createObjectURL) so we can observe the blob->url->img path and cleanup.

const MEDIA_URL = "/api/projects/p1/artifacts/a1/media";
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);
const PROMPT = "a serene mountain lake at golden hour, wide-angle";

let urlCounter = 0;
const createObjectURL = vi.fn(() => `blob:mock/${++urlCounter}`);
const revokeObjectURL = vi.fn();

beforeEach(() => {
  urlCounter = 0;
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

function renderViewer() {
  return renderWithProviders(
    <ImageViewer
      projectId="p1"
      artifactId="a1"
      title="Cover"
      createdAt="16.07.2026"
      content={PROMPT}
    />,
  );
}

describe("ImageViewer", () => {
  it("renders the fetched image with the prompt as alt text once loaded", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    renderViewer();

    const img = await screen.findByRole("img", { name: PROMPT });
    expect(img).toHaveAttribute("src", "blob:mock/1");
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });

  it("shows the prompt as the caption under the image", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    renderViewer();

    await screen.findByRole("img", { name: PROMPT });
    expect(screen.getByText(PROMPT)).toBeInTheDocument();
  });

  it("shows a loading placeholder before the blob arrives", async () => {
    server.use(
      http.get(MEDIA_URL, async () => {
        await delay(50);
        return pngResponse();
      }),
    );

    renderViewer();

    // Loading state is on-screen while the request is in flight.
    expect(
      screen.getByLabelText("Изображение загружается"),
    ).toBeInTheDocument();
    // ...and gives way to the image once the blob resolves.
    await screen.findByRole("img", { name: PROMPT });
    expect(
      screen.queryByLabelText("Изображение загружается"),
    ).not.toBeInTheDocument();
  });

  it("shows the not-found empty state on a 404 and hides zoom + download", async () => {
    server.use(
      http.get(MEDIA_URL, () =>
        HttpResponse.json({ detail: "no blob" }, { status: 404 }),
      ),
    );

    renderViewer();

    expect(
      await screen.findByText("изображение не найдено"),
    ).toBeInTheDocument();
    // Zoom pill is hidden in the empty state; download is disabled.
    expect(
      screen.queryByRole("button", { name: /По ширине/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\.png/ })).toBeDisabled();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("distinguishes a generic load failure from a 404", async () => {
    server.use(
      http.get(MEDIA_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderViewer();

    expect(
      await screen.findByText("не удалось загрузить изображение"),
    ).toBeInTheDocument();
  });

  it("downloads the already-fetched blob as <title>.png without a second request", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {});

    renderViewer();
    // Wait for the ready state (image present) — the download button enables
    // only once the objectURL backing it exists.
    await screen.findByRole("img", { name: PROMPT });
    const downloadBtn = screen.getByRole("button", { name: /\.png/ });
    expect(downloadBtn).toBeEnabled();

    await userEvent.click(downloadBtn);

    const anchor = clickSpy.mock.instances[0] as unknown as HTMLAnchorElement;
    expect(anchor.download).toBe("Cover.png");
    // Reuses the same objectURL already backing the <img> (no extra create).
    expect(anchor.getAttribute("href")).toBe("blob:mock/1");
    clickSpy.mockRestore();
  });

  it("revokes the objectURL when unmounted", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { unmount } = renderViewer();
    await screen.findByRole("img", { name: PROMPT });

    unmount();

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock/1");
  });
});
