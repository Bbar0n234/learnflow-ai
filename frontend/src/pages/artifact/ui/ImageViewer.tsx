import { useState } from "react";
import {
  Download,
  ExternalLink,
  ImageIcon,
  Minus,
  Plus,
  Maximize2,
} from "lucide-react";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import {
  MOCK_IMAGE_TITLE,
  MOCK_IMAGE_CREATED_AT,
  MOCK_IMAGE_CAPTION,
} from "../model/mock-artifact-data";

interface ImageViewerProps {
  title?: string;
  createdAt?: string;
}

const ZOOM_STEPS = [50, 75, 100, 125, 150, 200];

export function ImageViewer({
  title = MOCK_IMAGE_TITLE,
  createdAt = MOCK_IMAGE_CREATED_AT,
}: ImageViewerProps) {
  const [zoomIndex, setZoomIndex] = useState(2); // 100% default
  const zoom = ZOOM_STEPS[zoomIndex];

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
          <Button size="sm">
            <Download className="h-3.5 w-3.5" />
            .png
          </Button>
          <Button variant="outline" size="sm">
            <ExternalLink className="h-3.5 w-3.5" />
            Открыть в окне
          </Button>
        </div>
      </div>

      {/* Image display */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-muted/30 p-6">
        {/* Placeholder */}
        <div
          className="flex items-center justify-center overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all"
          style={{
            width: `${zoom}%`,
            maxWidth: "100%",
            aspectRatio: "4 / 3",
          }}
        >
          <div className="flex flex-col items-center gap-3 text-muted-foreground/40">
            <ImageIcon className="h-16 w-16" />
            <p className="font-mono text-xs">
              изображение недоступно в предпросмотре
            </p>
          </div>
        </div>

        {/* Zoom pill — absolute center bottom */}
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
      </div>

      {/* Caption */}
      <div className="shrink-0 border-t border-border px-6 py-3">
        <p className="text-xs text-muted-foreground">{MOCK_IMAGE_CAPTION}</p>
      </div>
    </div>
  );
}
