import { Link } from "react-router";
import { useEffect, useState } from "react";
import { FileText, ImageOff } from "lucide-react";
import { useArtifactMedia } from "@/shared/api/artifacts";
import { getArtifactCategory } from "@/shared/lib/artifact-category";
import { cn } from "@/shared/lib/utils";

/**
 * Карточка артефакта чата (`ArtifactPart`, ADR-032). Рендерится из блока
 * ленты по завершении хода (`groupFeedBlocks` — `shared/lib/agent-feed`), не
 * из `message.artifacts` (поле снято). Идентичность — путь: ссылка ведёт на
 * `?path=`, подпись — сам путь (уже относителен `artifacts/`).
 */
interface ArtifactCardArtifact {
  path: string;
  title: string;
  artifactType: string;
  kind: "created" | "updated";
  diff: { added: number; removed: number } | null;
}

interface ArtifactCardProps {
  artifact: ArtifactCardArtifact;
  projectId: string;
}

function artifactHref(projectId: string, path: string): string {
  return `/projects/${projectId}/artifacts?${new URLSearchParams({ path })}`;
}

export function ArtifactCard({ artifact, projectId }: ArtifactCardProps) {
  const isImage = getArtifactCategory(artifact.artifactType) === "image";

  return (
    <Link
      to={artifactHref(projectId, artifact.path)}
      className="mt-2 flex items-center gap-3 rounded-md bg-card p-3 transition-colors hover:bg-accent"
      style={{ borderLeft: "3px solid var(--ring)" }}
    >
      {isImage ? (
        <ArtifactThumbnail projectId={projectId} path={artifact.path} />
      ) : (
        <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{artifact.title}</p>
        <p className="truncate text-xs text-muted-foreground">
          {artifact.path}
        </p>
      </div>
      {artifact.kind === "updated" && (
        <span className="ml-auto shrink-0 rounded-full bg-secondary px-2.5 py-0.5 text-[0.66rem] font-medium text-secondary-foreground">
          обновлён
          {artifact.diff !== null &&
            ` · +${artifact.diff.added} −${artifact.diff.removed}`}
        </span>
      )}
    </Link>
  );
}

/**
 * Миниатюра 64×40 image-артефакта на месте типовой иконки. Использует тот же
 * media-ключ (`useArtifactMedia`), что и `ImageViewer` — react-query
 * дедуплицирует сеть между карточкой ленты и вьюером, повторный fetch не
 * происходит. Шиммер на время загрузки, фолбэк на иконку при ошибке/404
 * (консистентно с пустым состоянием `ImageViewer`), без битого `<img>`.
 */
function ArtifactThumbnail({
  projectId,
  path,
}: {
  projectId: string;
  path: string;
}) {
  const { data: blob, isError } = useArtifactMedia(projectId, path);

  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setObjectUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(blob);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blob]);

  return (
    <div
      aria-hidden="true"
      className={cn(
        "flex h-10 w-16 shrink-0 items-center justify-center overflow-hidden rounded-sm border border-border",
        !objectUrl &&
          !isError &&
          "animate-pulse bg-muted motion-reduce:animate-none",
        isError && "bg-muted",
      )}
    >
      {objectUrl ? (
        <img src={objectUrl} alt="" className="h-full w-full object-cover" />
      ) : isError ? (
        <ImageOff className="h-4 w-4 text-muted-foreground/60" />
      ) : null}
    </div>
  );
}
