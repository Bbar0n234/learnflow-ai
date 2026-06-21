import { setupServer } from "msw/node";

import { handlers } from "./handlers";

// One server for the whole run; lifecycle (listen/resetHandlers/close) is wired
// in src/test/setup.ts.
export const server = setupServer(...handlers);
