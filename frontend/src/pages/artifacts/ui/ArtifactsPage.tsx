import { Outlet } from "react-router";
import { ArtifactList } from "./ArtifactList";

/**
 * Split-panel layout for the Artifacts tab. Left: fixed 318px list; right:
 * flex-1 viewer (`<Outlet/>`).
 *
 * The viewer itself is selected by `?path=` (T2.2) rather than a route
 * segment (React Router does not match `/` inside one dynamic segment, and
 * `lecture-1/slides.md` needs to) — that dispatch (viewer vs. "выберите
 * артефакт" empty state) lives in `app/router.tsx`, not here: `pages/artifact`
 * is a sibling page slice, and the FSD boundaries lint (`eslint.config.mjs`)
 * disallows pages→pages imports, so this slice cannot render `ArtifactView`
 * directly. Composition of two page slices belongs to `app` (the one layer
 * allowed to import both), which is exactly what `<Outlet/>` here delegates
 * to.
 */
export function ArtifactsPage() {
  return (
    <div className="flex h-full">
      {/* List panel — 318px */}
      <aside className="w-[318px] shrink-0 overflow-y-auto border-r border-border">
        <ArtifactList />
      </aside>

      {/* Viewer panel */}
      <div className="flex min-w-0 flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
