import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { useUpdateProject } from "@/shared/api/projects";
import { useDeleteProject } from "@/shared/api/projects";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

interface ProjectActionsProps {
  projectId: string;
  projectName: string;
}

export function ProjectActions({
  projectId,
  projectName,
}: ProjectActionsProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();

  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newName, setNewName] = useState(projectName);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function handleRename(e: FormEvent) {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed || trimmed === projectName) {
      setRenameOpen(false);
      return;
    }
    setRenameError(null);
    updateProject.mutate(
      { id: projectId, data: { name: trimmed } },
      {
        onSuccess: () => setRenameOpen(false),
        onError: (err) => {
          logger.error("[Rename project error]", err);
          setRenameError(getApiErrorMessage(err));
        },
      },
    );
  }

  function handleDelete() {
    const isCurrentProject = location.pathname.includes(
      `/projects/${projectId}`,
    );
    setDeleteError(null);
    deleteProject.mutate(projectId, {
      onSuccess: () => {
        setDeleteOpen(false);
        if (isCurrentProject) {
          navigate("/");
        }
      },
      onError: (err) => {
        logger.error("[Delete project error]", err);
        setDeleteError(getApiErrorMessage(err));
      },
    });
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-xs"
              className="pointer-events-none opacity-0 group-hover/card:pointer-events-auto group-hover/card:opacity-100 focus-visible:pointer-events-auto focus-visible:opacity-100"
              onClick={(e) => e.preventDefault()}
            />
          }
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => {
              setNewName(projectName);
              setRenameError(null);
              setRenameOpen(true);
            }}
          >
            <Pencil />
            Переименовать
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={() => {
              setDeleteError(null);
              setDeleteOpen(true);
            }}
          >
            <Trash2 />
            Удалить
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Rename dialog */}
      <Dialog open={renameOpen} onOpenChange={(open) => setRenameOpen(open)}>
        <DialogContent>
          <form onSubmit={handleRename}>
            <DialogHeader>
              <DialogTitle>Переименовать проект</DialogTitle>
              <DialogDescription>
                Введите новое название проекта.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-2">
              <Input
                value={newName}
                onChange={(e) => {
                  setNewName(e.target.value);
                  setRenameError(null);
                }}
                autoFocus
              />
              {renameError && (
                <p className="text-sm text-destructive">{renameError}</p>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                type="button"
                onClick={() => setRenameOpen(false)}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                disabled={
                  !newName.trim() ||
                  newName.trim() === projectName ||
                  updateProject.isPending
                }
              >
                Сохранить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={(open) => setDeleteOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Удалить проект</DialogTitle>
            <DialogDescription>
              Удалить «{projectName}»? Все чаты, артефакты и сфера знаний
              проекта будут удалены. Это действие нельзя отменить.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive">{deleteError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteProject.isPending}
            >
              Удалить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
