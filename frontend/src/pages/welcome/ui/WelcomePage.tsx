import { useState } from "react";
import { useNavigate } from "react-router";
import { Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Illustration } from "@/shared/ui/Illustration";
import { Input } from "@/shared/ui/input";
import { SphereOrb } from "@/shared/ui/SphereOrb";
import { Wordmark } from "@/shared/ui/Wordmark";
import { useCreateProject, useProjects } from "@/shared/api/projects";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

/** Orb opacity based on project staleness (days since last update). */
function getOrbOpacity(updatedAt: string): number {
  const ageDays =
    (Date.now() - new Date(updatedAt).getTime()) / (1000 * 60 * 60 * 24);
  if (ageDays < 1) return 1.0;
  if (ageDays < 3) return 0.8;
  if (ageDays < 14) return 0.6;
  return 0.4;
}

export function WelcomePage() {
  const navigate = useNavigate();
  const { data } = useProjects();

  const recentProjects = [...(data?.items ?? [])]
    .sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    )
    .slice(0, 3);
  const mostRecent = recentProjects[0];

  const [createOpen, setCreateOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const createProject = useCreateProject();

  async function handleCreate() {
    if (!projectName.trim()) return;
    setCreateError(null);
    try {
      const project = await createProject.mutateAsync({
        name: projectName.trim(),
      });
      setProjectName("");
      setCreateOpen(false);
      navigate(`/projects/${project.id}`);
    } catch (err: unknown) {
      logger.error("[WelcomePage] create project failed", err);
      setCreateError(getApiErrorMessage(err));
    }
  }

  return (
    <div className="flex h-full items-center justify-center px-8 py-12">
      <div className="flex flex-col items-center gap-6 text-center">
        {/* Wordmark — полная форма (из T2) */}
        <h1 className="text-4xl">
          <Wordmark />
        </h1>

        {/* Hero-врезка 460×270 (из T3) */}
        <Illustration
          scene="welcome-hero"
          alt="Welcome to LearnFlowAI"
          className="mx-auto h-[270px] w-full max-w-[460px] object-contain"
        />

        {/* Serif-приветствие 38px */}
        <h2 className="font-serif text-[38px] font-semibold leading-tight text-foreground">
          Добро пожаловать
        </h2>

        {/* Подзаголовок */}
        <p className="-mt-3 text-base text-muted-foreground">
          Ваш ИИ-помощник для обучения
        </p>

        {/* CTA */}
        <div className="flex gap-3">
          <Button size="lg" onClick={() => setCreateOpen(true)}>
            <Plus />
            Новый проект
          </Button>
          {mostRecent && (
            <Button
              variant="outline"
              size="lg"
              onClick={() => navigate(`/projects/${mostRecent.id}`)}
            >
              Продолжить …
            </Button>
          )}
        </div>

        {/* Карточки последних проектов */}
        {recentProjects.length > 0 && (
          <div className="mt-2 flex gap-4">
            {recentProjects.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={() => navigate(`/projects/${project.id}`)}
                className="group flex w-[220px] flex-col items-start gap-3 rounded-xl border border-border bg-card p-4 text-left transition-colors hover:border-ring/40 hover:bg-muted"
              >
                <div style={{ opacity: getOrbOpacity(project.updated_at) }}>
                  <SphereOrb size={20} />
                </div>
                <span className="line-clamp-2 font-serif text-sm font-semibold leading-snug text-foreground">
                  {project.name}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Диалог создания проекта */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Новый проект</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="Название проекта"
            value={projectName}
            onChange={(e) => {
              setProjectName(e.target.value);
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
              disabled={!projectName.trim() || createProject.isPending}
            >
              Создать
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
