import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { AxiosError } from "axios";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { createTestQueryClient } from "@/test/test-utils";

import { isArtifactMediaNotFound, useArtifactMedia } from "./artifacts";

// Integration: the image media fetch layer (feat-010, T2.1). `getArtifactMedia`
// pulls the binary from `.../artifacts/:id/media` as a Blob under JWT (axios
// interceptor), `useArtifactMedia` caches it, `isArtifactMediaNotFound`
// classifies a 404 (empty state) apart from network/500 errors. Network is
// mocked with MSW; a Blob response carries its mime via Content-Type.

const MEDIA_URL = "/api/projects/p1/artifacts/a1/media";

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
  artifactId: string | undefined,
) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return renderHook(() => useArtifactMedia(projectId, artifactId), { wrapper });
}

describe("isArtifactMediaNotFound", () => {
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

  it("is true for a 404 (blob absent)", () => {
    expect(isArtifactMediaNotFound(axiosErrorWith(404))).toBe(true);
  });

  it("is false for a non-404 status (network/server error)", () => {
    expect(isArtifactMediaNotFound(axiosErrorWith(500))).toBe(false);
  });

  it("is false for a non-Axios error", () => {
    expect(isArtifactMediaNotFound(new Error("boom"))).toBe(false);
    expect(isArtifactMediaNotFound(null)).toBe(false);
  });
});

describe("useArtifactMedia", () => {
  it("resolves the media blob from the endpoint on success", async () => {
    server.use(http.get(MEDIA_URL, () => pngResponse()));

    const { result } = renderMediaHook("p1", "a1");

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

    const { result } = renderMediaHook("p1", "a1");

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(isArtifactMediaNotFound(result.current.error)).toBe(true);
  });

  it("stays idle and issues no request when an id is missing", async () => {
    // No handler registered: any request would trip MSW's onUnhandledRequest:error.
    const { result } = renderMediaHook("p1", undefined);

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.data).toBeUndefined();
  });
});
