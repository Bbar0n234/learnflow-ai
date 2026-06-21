import { Outlet } from "react-router";
import { ArtifactList } from "./ArtifactList";

/**
 * Split-panel layout for the Artifacts tab (T4d).
 * Left: fixed 318px list; right: flex-1 viewer (Outlet).
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
