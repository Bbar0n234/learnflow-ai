import { Outlet, Link } from "react-router";

export function AppLayout() {
  return (
    <div className="flex h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-sidebar p-4">
        <h2 className="mb-4 text-lg font-semibold text-sidebar-foreground">
          LearnFlowAI
        </h2>
        <nav className="flex flex-col gap-2">
          <Link
            to="/"
            className="rounded-md px-3 py-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent"
          >
            Home
          </Link>
          <Link
            to="/projects/demo"
            className="rounded-md px-3 py-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent"
          >
            Demo Project
          </Link>
        </nav>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
