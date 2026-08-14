import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { AxiosError } from "axios";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "@/test/msw/server";
import { createTestQueryClient } from "@/test/test-utils";

import {
  downloadArtifact,
  getArtifact,
  getArtifactMedia,
  isArtifactNotFound,
  useArtifact,
  useArtifactMedia,
} from "./artifacts";

// Integration: the image media fetch layer (feat-011, T2.1). `getArtifactMedia`
// pulls the binary from `.../artifacts/media?path=…` as a Blob under JWT
// (axios interceptor), `useArtifactMedia` caches it, `isArtifactNotFound`
// classifies a 404 (empty state) apart from network/500 errors. Network is
// mocked with MSW; a Blob response carries its mime via Content-Type.

const MEDIA_URL = "/api/projects/p1/artifacts/media";

// 8-byte PNG signature — a stand-in binary body; its size/type are asserted.
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
]);

function pngResponse() {
  return new HttpResponse(PNG_BYTES, {
    headers: { "Content-Type": "image/png" },
  });
}

function renderMediaHook(
  projectId: string | undefined,
  path: string | undefined,
) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return renderHook(() => useArtifactMedia(projectId, path), { wrapper });
}

describe("isArtifactNotFound", () => {
  function axiosErrorWith(status: number): AxiosError {
    const err = new AxiosError("Request failed");
    err.response = {
      status,
      statusText: "",
      data: null,
      headers: {},
      config: { headers: {} as never },
    };
    return err;
  }

  it("is true for a 404 (path/blob absent)", () => {
    expect(isArtifactNotFound(axiosErrorWith(404))).toBe(true);
  });

  it("is false for a non-404 status (network/server error)", () => {
    expect(isArtifactNotFound(axiosErrorWith(500))).toBe(false);
  });

  it("is false for a non-Axios error", () => {
    expect(isArtifactNotFound(new Error("boom"))).toBe(false);
    expect(isArtifactNotFound(null)).toBe(false);
  });
});

describe("useArtifactMedia", () => {
  it("resolves the media blob from the endpoint on success", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { result } = renderMediaHook("p1", "lecture-1/cover.png");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const blob = result.current.data;
    // A non-empty Blob carrying the server mime — enough to build an objectURL;
    // byte-exact size isn't asserted (the jsdom transport re-encodes high bytes).
    expect(blob).toBeInstanceOf(Blob);
    expect(blob?.size).toBeGreaterThan(0);
    expect(blob?.type).toBe("image/png");
  });

  it("surfaces a 404 as a not-found error the predicate recognises", async () => {
    server.use(
      http.get(MEDIA_URL, () =>
        HttpResponse.json({ detail: "no blob" }, { status: 404 }),
      ),
    );

    const { result } = renderMediaHook("p1", "lecture-1/cover.png");

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(isArtifactNotFound(result.current.error)).toBe(true);
  });

  it("stays idle and issues no request when a path is missing", async () => {
    // No handler registered: any request would trip MSW's onUnhandledRequest:error.
    const { result } = renderMediaHook("p1", undefined);

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });
});

// Идентичность артефакта — путь (ADR-032), и он едет query-параметром, а не
// сегментом URL: слэши вложенности иначе не пережили бы ни роутинг, ни фабрику
// ключей кэша.

const DETAIL_URL = "/api/projects/p1/artifacts";
const DOWNLOAD_URL = "/api/projects/p1/artifacts/download";

describe("адресация артефакта путём", () => {
  it("детали запрашиваются с полным путём, включая поддиректории", async () => {
    let seenPath: string | null = null;
    server.use(
      http.get(DETAIL_URL, ({ request }) => {
        seenPath = new URL(request.url).searchParams.get("path");
        return HttpResponse.json({
          path: "lecture-1/slides.md",
          title: "Слайды",
          type: "md",
          updated_at: "2026-02-01T12:00:00Z",
          content: "слайд",
        });
      }),
    );

    const detail = await getArtifact("p1", "lecture-1/slides.md");

    expect(seenPath).toBe("lecture-1/slides.md");
    expect(detail.title).toBe("Слайды");
  });

  it("медиа запрашивается тем же путём, без сегмента-идентификатора", async () => {
    let seenPath: string | null = null;
    server.use(
      http.get(MEDIA_URL, ({ request }) => {
        seenPath = new URL(request.url).searchParams.get("path");
        return pngResponse();
      }),
    );

    await getArtifactMedia("p1", "lecture-1/cover.png");

    expect(seenPath).toBe("lecture-1/cover.png");
  });

  it("одноимённые файлы разной вложенности не делят кэш", async () => {
    // Ключ кэша строится из пути: если бы в него попадало только имя файла,
    // корневой `slides.md` и `lecture-1/slides.md` показывали бы одно и то же.
    server.use(
      http.get(DETAIL_URL, ({ request }) => {
        const path = new URL(request.url).searchParams.get("path") ?? "";
        return HttpResponse.json({
          path,
          title: path === "slides.md" ? "Корневые слайды" : "Слайды лекции 1",
          type: "md",
          updated_at: "2026-02-01T12:00:00Z",
          content: path,
        });
      }),
    );
    const queryClient = createTestQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const root = renderHook(() => useArtifact("p1", "slides.md"), { wrapper });
    const nested = renderHook(() => useArtifact("p1", "lecture-1/slides.md"), {
      wrapper,
    });

    await waitFor(() => expect(root.result.current.isSuccess).toBe(true));
    await waitFor(() => expect(nested.result.current.isSuccess).toBe(true));
    expect(root.result.current.data?.title).toBe("Корневые слайды");
    expect(nested.result.current.data?.title).toBe("Слайды лекции 1");
  });
});

describe("downloadArtifact", () => {
  /** Имя, которое браузер получил бы как имя сохраняемого файла. */
  function captureDownloadName(): { name: string | undefined } {
    const captured: { name: string | undefined } = { name: undefined };
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      captured.name = this.download;
    });
    return captured;
  }

  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:mock/download");
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("сохраняет файл под именем из Content-Disposition", async () => {
    server.use(
      http.get(DOWNLOAD_URL, () =>
        HttpResponse.text("тело", {
          headers: {
            "Content-Disposition": 'attachment; filename="konspekt.md"',
          },
        }),
      ),
    );
    const captured = captureDownloadName();

    await downloadArtifact("p1", "lecture-1/konspekt.md");

    expect(captured.name).toBe("konspekt.md");
  });

  it("без заголовка имени берёт последний сегмент пути, а не выдуманное расширение", async () => {
    // Формата экспорта у файловой модели нет (`format` из REST ушёл): имя
    // берётся из самого пути, иначе `.md`-конспект сохранялся бы как `.pdf`.
    server.use(http.get(DOWNLOAD_URL, () => HttpResponse.text("тело")));
    const captured = captureDownloadName();

    await downloadArtifact("p1", "lecture-1/konspekt.md");

    expect(captured.name).toBe("konspekt.md");
  });
});
