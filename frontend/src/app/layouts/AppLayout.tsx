import { Outlet } from "react-router";
import { PanelLeft } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { Sidebar } from "../components/Sidebar";

export function AppLayout() {
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  return (
    <div className="flex h-screen">
      <aside
        className={cn(
          "shrink-0 border-r border-border bg-sidebar transition-all duration-200 overflow-hidden",
          sidebarOpen ? "w-[252px]" : "w-0 border-r-0",
        )}
      >
        <Sidebar />
      </aside>
      <main
        className="flex-1 overflow-auto"
        style={{ scrollbarGutter: "stable" }}
      >
        {!sidebarOpen && (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleSidebar}
            className="absolute top-3 left-3 z-10"
          >
            <PanelLeft className="h-4 w-4" />
          </Button>
        )}
        <Outlet />
      </main>
    </div>
  );
}
