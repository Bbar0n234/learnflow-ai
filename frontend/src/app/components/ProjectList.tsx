import { useProjects } from "@/shared/api/projects";
import { Skeleton } from "@/shared/ui/skeleton";
import { ErrorCard } from "@/shared/ui/StateScreen";
import { ProjectCard } from "./ProjectCard";

export function ProjectList() {
  const { data, isLoading, isError, refetch } = useProjects();

  if (isLoading) {
    return (
      <div className="flex flex-col gap-0.5">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
          <Skeleton className="h-3 w-[70%]" />
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5">
          <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
          <Skeleton className="h-3 w-[52%]" />
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5">
          <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
          <Skeleton className="h-3 w-[61%]" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorCard
        className="flex-col items-start justify-start gap-2 px-3 py-2"
        message="Не удалось загрузить проекты"
        onRetry={() => void refetch()}
      />
    );
  }

  if (!data?.items.length) {
    return (
      <p className="px-3 py-1.5 text-xs text-muted-foreground">
        Проектов пока нет
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
