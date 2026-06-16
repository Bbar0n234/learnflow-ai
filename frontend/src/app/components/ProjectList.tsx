import { useProjects } from "@/shared/api/projects";
import { ProjectCard } from "./ProjectCard";

export function ProjectList() {
  const { data, isLoading, isError } = useProjects();

  if (isLoading) {
    return (
      <p className="px-3 py-1.5 text-xs text-muted-foreground">Loading...</p>
    );
  }

  if (isError) {
    return (
      <p className="px-3 py-1.5 text-xs text-destructive">
        Failed to load projects
      </p>
    );
  }

  if (!data?.items.length) {
    return (
      <p className="px-3 py-1.5 text-xs text-muted-foreground">
        No projects yet
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-0.5">
      {data.items.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
