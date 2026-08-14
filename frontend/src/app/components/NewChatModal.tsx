import { useState } from "react";
import { useNavigate } from "react-router";
import { Plus } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { LoadingState, ErrorCard } from "@/shared/ui/StateScreen";
import { useProjects, type Project } from "@/shared/api/projects";
import { CreateProjectModal } from "./CreateProjectModal";

interface NewChatModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Модалка выбора проекта для входа «+ Новый чат» из сайдбара (единственный хост — Sidebar).
 * Показывается всегда, включая случай, когда пользователь уже внутри проекта.
 */
export function NewChatModal({ open, onOpenChange }: NewChatModalProps) {
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useProjects();
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  const projects = data?.items ?? [];

  function goToComposer(projectId: string) {
    onOpenChange(false);
    navigate(`/projects/${projectId}/chats/new`);
  }

  function handleProjectCreated(project: Project) {
    setCreateProjectOpen(false);
    goToComposer(project.id);
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новый чат</DialogTitle>
            <DialogDescription>
              Выберите проект, в котором начать чат.
            </DialogDescription>
          </DialogHeader>

          {isLoading && (
            <LoadingState label="Загрузка проектов…" className="py-2" />
          )}
          {isError && (
            <ErrorCard
              message="Не удалось загрузить список проектов"
              onRetry={() => void refetch()}
            />
          )}
          {!isLoading && !isError && projects.length === 0 && (
            <div className="flex flex-col items-center gap-3 py-2 text-center">
              <p className="text-sm text-muted-foreground">
                У вас пока нет проектов — чат живёт внутри проекта.
              </p>
              <Button onClick={() => setCreateProjectOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Создать проект
              </Button>
            </div>
          )}
          {!isLoading && !isError && projects.length > 0 && (
            <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto">
              {projects.map((project) => (
                <Button
                  key={project.id}
                  variant="ghost"
                  className="w-full justify-start"
                  onClick={() => goToComposer(project.id)}
                >
                  <span className="h-2 w-2 shrink-0 rounded-full bg-brand-lavender" />
                  <span className="truncate">{project.name}</span>
                </Button>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <CreateProjectModal
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        onCreated={handleProjectCreated}
      />
    </>
  );
}
