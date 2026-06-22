// Local test helpers (not part of the frozen harness): build an SSE
// `text/event-stream` ReadableStream body for MSW, and craft fake JWTs so
// ensureFreshToken() resolves without hitting the network.

/** Encode one SSE frame for the agent stream protocol (doc/tech/streaming.md). */
export function sseFrame(event: unknown): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

/**
 * A ReadableStream<Uint8Array> of raw SSE frames, suitable as an
 * `new HttpResponse(body, { headers: { "Content-Type": "text/event-stream" } })`.
 * Pass already-encoded strings (use `sseFrame`) — including deliberately
 * malformed ones — to exercise the reader's framing/parse paths.
 */
export function sseResponseStream(
  frames: string[],
): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
      controller.close();
    },
  });
}

/** A non-expired JWT whose payload decodes to `{ exp }` `nowSeconds + ttl`. */
export function fakeJwt(ttlSeconds = 3600): string {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const exp = Math.floor(Date.now() / 1000) + ttlSeconds;
  const payload = btoa(JSON.stringify({ exp }));
  return `${header}.${payload}.signature`;
}
