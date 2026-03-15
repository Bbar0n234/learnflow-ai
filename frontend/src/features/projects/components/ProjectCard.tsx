import { NavLink } from "react-router";
import { FolderOpen } from "lucide-react";
import type { Project } from "@/shared/api/types";
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
        <FolderOpen className="h-4 w-4 shrink-0" />
        <span className="truncate">{project.name}</span>
      </NavLink>
      <div className="absolute right-1">
        <ProjectActions projectId={project.id} projectName={project.name} />
      </div>
    </div>
  );
}
