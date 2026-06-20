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
      {/* Header — 52–58px per handoff; project name + tabs inline.
          T4e will add serif font, sphere-status chip, and tab underline styling. */}
      <header className="flex h-[56px] items-center gap-6 border-b border-border px-6">
        <h1 className="shrink-0 text-sm font-semibold text-foreground">
          {projectName}
        </h1>
        <nav className="flex gap-1">
          <NavLink
            to={`/projects/${id}`}
            end
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Чаты
          </NavLink>
          <NavLink
            to={`/projects/${id}/sphere`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Сфера
          </NavLink>
          <NavLink
            to={`/projects/${id}/artifacts`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Артефакты
          </NavLink>
          <NavLink
            to={`/projects/${id}/settings`}
            className={({ isActive }) =>
              `rounded-md px-3 py-1.5 text-sm ${isActive ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`
            }
          >
            Настройки
          </NavLink>
        </nav>
      </header>
      <div className="flex-1 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
