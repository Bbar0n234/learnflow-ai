import { Outlet, NavLink, useParams, useMatch } from "react-router";
import { useProject } from "@/shared/api/projects";

export function ProjectLayout() {
  const { id } = useParams();
  const { data: project, isLoading } = useProject(id!);
  const isChatView = useMatch("/projects/:id/chats/:cid");

  const projectName = isLoading ? "Loading..." : (project?.name ?? id);

  if (isChatView) {
    return (
      <div className="flex h-full flex-col">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border px-6 py-4">
        <h1 className="mb-3 text-xl font-semibold">{projectName}</h1>
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
          <NavLink
            to={`/projects/${id}/settings`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Settings
          </NavLink>
        </nav>
      </header>
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
