import { NavLink } from "react-router";
import type { Project } from "@/shared/api/projects";
import { cn } from "@/shared/lib/utils";
import { ProjectActions } from "./ProjectActions";

interface ProjectCardProps {
  project: Project;
}

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <div className="group/card relative flex items-center">
      <NavLink
        to={`/projects/${project.id}`}
        className={({ isActive }) =>
          cn(
            "flex flex-1 items-center gap-2 rounded-md px-3 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent",
            isActive && "bg-sidebar-accent font-medium",
          )
        }
      >
        {/* Status dot — color reflects project activity; full logic arrives with backend status field */}
        <span className="h-2 w-2 shrink-0 rounded-full bg-brand-lavender" />
        <span className="truncate">{project.name}</span>
      </NavLink>
      <div className="absolute right-1">
        <ProjectActions projectId={project.id} projectName={project.name} />
      </div>
    </div>
  );
}
