import { Outlet, NavLink, useParams } from "react-router";

export function ProjectLayout() {
  const { id } = useParams();

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border px-6 py-4">
        <h1 className="mb-3 text-xl font-semibold">Project: {id}</h1>
        <nav className="flex gap-4">
          <NavLink
            to={`/projects/${id}`}
            end
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Chats
          </NavLink>
          <NavLink
            to={`/projects/${id}/sphere`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Sphere
          </NavLink>
          <NavLink
            to={`/projects/${id}/artifacts`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Artifacts
          </NavLink>
        </nav>
      </header>
      <div className="flex-1 overflow-auto p-6">
        <Outlet />
      </div>
    </div>
  );
}
