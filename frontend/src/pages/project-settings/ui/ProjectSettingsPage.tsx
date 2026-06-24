import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";
import { Button } from "@/shared/ui/button";
import {
  useProject,
  useUpdateProject,
  useDeleteProject,
} from "@/shared/api/projects";

export function ProjectSettingsPage() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId!);
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();
  const [name, setName] = useState("");
  const [nameDirty, setNameDirty] = useState(false);

  useEffect(() => {
    if (project) {
      setName(project.name);
      setNameDirty(false);
    }
  }, [project]);

  function handleSaveName() {
    if (!projectId || !name.trim()) return;
    updateProject.mutate(
      { id: projectId, data: { name: name.trim() } },
      { onSuccess: () => setNameDirty(false) },
    );
  }

  function handleDelete() {
    if (!projectId) return;
    deleteProject.mutate(projectId, {
      onSuccess: () => navigate("/"),
    });
  }

  return (
    <div className="mx-auto max-w-[640px] px-6 py-8">
      <h2 className="mb-6 font-serif text-xl font-semibold text-foreground">
        Настройки проекта
      </h2>
      <div className="space-y-4">
        <section className="rounded-xl border border-border bg-card p-5">
          <ModelSelector scope="project" projectId={projectId} />
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <MCPServersSection scope="project" projectId={projectId} />
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            Имя проекта
          </label>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
              value={name}
              maxLength={100}
              onChange={(e) => {
                setName(e.target.value);
                setNameDirty(true);
              }}
            />
            <Button
              size="sm"
              onClick={handleSaveName}
              disabled={!nameDirty || updateProject.isPending || !name.trim()}
            >
              {updateProject.isPending ? "Сохраняем…" : "Сохранить"}
            </Button>
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <p className="mb-0.5 text-sm font-medium text-foreground">
            Удалить проект
          </p>
          <p className="mb-3 text-xs text-muted-foreground">
            Необратимо — все чаты, артефакты и данные сферы будут потеряны.
          </p>
          <button
            onClick={handleDelete}
            disabled={deleteProject.isPending}
            className="text-sm text-destructive-warm underline-offset-2 hover:underline disabled:opacity-50"
          >
            {deleteProject.isPending ? "Удаляем…" : "Удалить проект…"}
          </button>
        </section>
      </div>
    </div>
  );
}
