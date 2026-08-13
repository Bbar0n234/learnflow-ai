import { Outlet, NavLink, useParams, useMatch } from "react-router";
import { useProject } from "@/shared/api/projects";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

// T6b mock — чип состояния сферы (L0.5, без бэкенд-контракта, group B stub)
const SPHERE_CHIP_VERSION = "v2.4.1";
const SPHERE_CHIP_STATUS = "растёт";

export function ProjectLayout() {
  const { id } = useParams();
  const { data: project, isLoading } = useProject(id!);
  const isChatView = useMatch("/projects/:id/chats/:cid");

  const projectName = isLoading ? "Loading..." : (project?.name ?? id);

  if (isChatView) {
    // `overflow-hidden` — тот же страж переполнения, что у остальных вкладок
    // проекта (ниже): чат сам управляет своей прокруткой, наружу переполнение
    // не выпускает, иначе внешний контейнер получает второй скролл в пустоту.
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <Outlet />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-[56px] items-center gap-6 border-b border-border px-6">
        <div className="flex shrink-0 items-center gap-2.5">
          <h1 className="font-serif text-sm font-semibold text-foreground">
            {projectName}
          </h1>
          {/* Чип состояния сферы — T6b (mock, L0.5, без бэкенд-контракта, group B stub) */}
          {SHOW_GROUP_B_STUBS && (
            <span className="rounded-full bg-secondary px-2 py-0.5 font-mono text-[10px] text-secondary-foreground">
              {SPHERE_CHIP_VERSION} · {SPHERE_CHIP_STATUS}
            </span>
          )}
        </div>
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
