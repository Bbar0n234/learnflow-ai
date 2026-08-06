import { useEffect, useState } from "react";
import { Download, ImageOff, Minus, Plus, Maximize2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import {
  useArtifactMedia,
  isArtifactMediaNotFound,
} from "@/shared/api/artifacts";

interface ImageViewerProps {
  projectId?: string;
  artifactId?: string;
  title?: string;
  createdAt?: string;
  content?: string;
}

const ZOOM_STEPS = [50, 75, 100, 125, 150, 200];

export function ImageViewer({
  projectId,
  artifactId,
  title,
  createdAt,
  content,
}: ImageViewerProps) {
  const [zoomIndex, setZoomIndex] = useState(2); // 100% default
  const zoom = ZOOM_STEPS[zoomIndex];

  const {
    data: blob,
    isError,
    error,
  } = useArtifactMedia(projectId, artifactId);

  // Blob иммутабелен по построению (перегенерация даёт новый артефакт/id) —
  // objectURL живёт, пока жив компонент, и освобождается на unmount/смену blob.
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

  const notFound = isError && isArtifactMediaNotFound(error);
  const isReady = !!objectUrl;
  const isEmpty = isError && !isReady;

  function handleDownload() {
    if (!blob || !objectUrl) return;
    const ext = blob.type.split("/")[1] || "png";
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = `${title ?? "image"}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div className="min-w-0 flex-1 pr-4">
          <h2 className="font-serif text-[26px] font-semibold leading-tight text-foreground">
            {title}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            image · {createdAt}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm" disabled={!isReady} onClick={handleDownload}>
            <Download className="h-3.5 w-3.5" />
            .png
          </Button>
        </div>
      </div>

      {/* Image display */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-6">
        <div
          className="flex items-center justify-center overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all"
          style={{
            width: `${zoom}%`,
            maxWidth: "100%",
            aspectRatio: "4 / 3",
          }}
        >
          {isReady ? (
            <img
              src={objectUrl}
              alt={content}
              className="h-full w-full object-cover"
            />
          ) : isEmpty ? (
            <div className="flex flex-col items-center gap-3 text-muted-foreground/40">
              <ImageOff className="h-16 w-16" />
              <p className="font-mono text-xs">
                {notFound
                  ? "изображение не найдено"
                  : "не удалось загрузить изображение"}
              </p>
            </div>
          ) : (
            <div
              className="h-full w-full animate-pulse bg-muted motion-reduce:animate-none"
              aria-label="Изображение загружается"
            />
          )}
        </div>

        {/* Zoom pill — absolute center bottom, скрыт в пустом состоянии */}
        {!isEmpty && (
          <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-full border border-border bg-card px-2 py-1 shadow-sm">
            <button
              type="button"
              onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
              disabled={zoomIndex === 0}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-foreground transition-colors hover:bg-muted",
                zoomIndex === 0 && "cursor-not-allowed opacity-40",
              )}
            >
              <Minus className="h-3 w-3" />
            </button>
            <span className="min-w-[3.5rem] text-center font-mono text-xs text-foreground">
              {zoom}%
            </span>
            <button
              type="button"
              onClick={() =>
                setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))
              }
              disabled={zoomIndex === ZOOM_STEPS.length - 1}
              className={cn(
                "flex h-6 w-6 items-center justify-center rounded-full text-foreground transition-colors hover:bg-muted",
                zoomIndex === ZOOM_STEPS.length - 1 &&
                  "cursor-not-allowed opacity-40",
              )}
            >
              <Plus className="h-3 w-3" />
            </button>
            <div className="mx-1 h-3 w-px bg-border" />
            <button
              type="button"
              onClick={() => setZoomIndex(2)}
              className="flex h-6 items-center gap-1 rounded-full px-2 text-xs text-foreground transition-colors hover:bg-muted"
            >
              <Maximize2 className="h-3 w-3" />
              По ширине
            </button>
          </div>
        )}
      </div>

      {/* Caption — content артефакта (prompt) */}
      <div className="shrink-0 border-t border-border px-6 py-3">
        <p className="text-xs text-muted-foreground">{content}</p>
      </div>
    </div>
  );
}
