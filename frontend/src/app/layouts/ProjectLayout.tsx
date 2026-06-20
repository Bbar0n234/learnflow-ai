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
      <header className="flex h-[56px] items-center gap-6 border-b border-border px-6">
        <h1 className="shrink-0 font-serif text-sm font-semibold text-foreground">
          {projectName}
        </h1>
        <nav className="flex h-full gap-1">
          <NavLink
            to={`/projects/${id}`}
            end
            className={({ isActive }) =>
              `flex h-full items-center px-3 text-sm transition-colors ${
                isActive
                  ? "text-primary [box-shadow:inset_0_-2px_0_var(--ring)]"
                  : "text-muted-foreground hover:text-foreground"
              }`
            }
          >
            Чаты
          </NavLink>
          <NavLink
            to={`/projects/${id}/sphere`}
            className={({ isActive }) =>
              `flex h-full items-center px-3 text-sm transition-colors ${
                isActive
                  ? "text-primary [box-shadow:inset_0_-2px_0_var(--ring)]"
                  : "text-muted-foreground hover:text-foreground"
              }`
            }
          >
            Сфера
          </NavLink>
          <NavLink
            to={`/projects/${id}/artifacts`}
            className={({ isActive }) =>
              `flex h-full items-center px-3 text-sm transition-colors ${
                isActive
                  ? "text-primary [box-shadow:inset_0_-2px_0_var(--ring)]"
                  : "text-muted-foreground hover:text-foreground"
              }`
            }
          >
            Артефакты
          </NavLink>
          <NavLink
            to={`/projects/${id}/settings`}
            className={({ isActive }) =>
              `flex h-full items-center px-3 text-sm transition-colors ${
                isActive
                  ? "text-primary [box-shadow:inset_0_-2px_0_var(--ring)]"
                  : "text-muted-foreground hover:text-foreground"
              }`
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
