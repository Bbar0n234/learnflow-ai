import { useState } from "react";
import { useNavigate } from "react-router";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import { useCreateProject } from "@/shared/api/projects";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

interface CreateProjectModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateProjectModal({
  open,
  onOpenChange,
}: CreateProjectModalProps) {
  const [name, setName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const navigate = useNavigate();
  const createProject = useCreateProject();

  async function handleCreate() {
    if (!name.trim()) return;
    setCreateError(null);
    try {
      const data = await createProject.mutateAsync({ name: name.trim() });
      setName("");
      onOpenChange(false);
      navigate(`/projects/${data.id}`);
    } catch (err: unknown) {
      logger.error("[CreateProject error]", err);
      setCreateError(getApiErrorMessage(err));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Project</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Project name"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setCreateError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleCreate();
          }}
        />
        {createError && (
          <p className="text-sm text-destructive">{createError}</p>
        )}
        <DialogFooter>
          <Button
            onClick={handleCreate}
            disabled={!name.trim() || createProject.isPending}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
