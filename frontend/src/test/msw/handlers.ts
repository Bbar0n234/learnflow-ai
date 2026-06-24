import type { RequestHandler } from "msw";

// Default (global) handlers are intentionally empty: each test declares the
// network it expects via `server.use(...)`, keeping intent local. The agent
// SSE stream is mocked with MSW's native streaming response (a ReadableStream
// body of `text/event-stream`) — see conventions.md § Frontend.
export const handlers: RequestHandler[] = [];
