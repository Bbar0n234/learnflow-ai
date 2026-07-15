import { Link } from "react-router";
import { useEffect, useState } from "react";
import { FileText, ImageOff } from "lucide-react";
import { useArtifactMedia } from "@/shared/api/artifacts";
import { cn } from "@/shared/lib/utils";

interface ArtifactCardProps {
  artifact: { id: string; title: string; type: string };
  projectId: string;
}

export function ArtifactCard({ artifact, projectId }: ArtifactCardProps) {
  const isImage = artifact.type === "image";

  return (
    <Link
      to={`/projects/${projectId}/artifacts/${artifact.id}`}
      className="mt-2 flex items-center gap-3 rounded-md bg-card p-3 transition-colors hover:bg-accent"
      style={{ borderLeft: "3px solid var(--ring)" }}
    >
      {isImage ? (
        <ArtifactThumbnail projectId={projectId} artifactId={artifact.id} />
      ) : (
        <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
      )}
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{artifact.title}</p>
        <p className="text-xs text-muted-foreground">{artifact.type}</p>
      </div>
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
  artifactId,
}: {
  projectId: string;
  artifactId: string;
}) {
  const { data: blob, isError } = useArtifactMedia(projectId, artifactId);

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
        !objectUrl && !isError && "animate-pulse bg-muted",
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
