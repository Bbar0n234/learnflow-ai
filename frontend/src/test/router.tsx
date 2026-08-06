// Local test helper (not part of the frozen harness). Page components read route
// params via react-router's useParams and render <Link>, so they must be mounted
// inside a router. This wraps a single page element in a MemoryRouter at a given
// path, letting the page's useParams() resolve. Compose with renderWithProviders
// for the QueryClient.

import { MemoryRouter, Route, Routes } from "react-router";
import type { ReactElement } from "react";

interface RouterAtOptions {
  /** Route pattern with params, e.g. "/projects/:id/artifacts". */
  path: string;
  /** Concrete URL to start at, e.g. "/projects/p1/artifacts". */
  entry: string;
}

/** Wrap a page element in a MemoryRouter so its useParams() resolves. */
export function routerAt(
  element: ReactElement,
  { path, entry }: RouterAtOptions,
): ReactElement {
  return (
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path={path} element={element} />
      </Routes>
    </MemoryRouter>
  );
}
