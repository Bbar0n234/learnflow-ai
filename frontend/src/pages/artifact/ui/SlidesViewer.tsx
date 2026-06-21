import { useState } from "react";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { SphereOrb } from "@/shared/ui/SphereOrb";
import { cn } from "@/shared/lib/utils";
import {
  MOCK_SLIDES_TITLE,
  MOCK_SLIDES_CREATED_AT,
  MOCK_SLIDES,
} from "../model/mock-artifact-data";

interface SlidesViewerProps {
  title?: string;
  createdAt?: string;
}

export function SlidesViewer({
  title = MOCK_SLIDES_TITLE,
  createdAt = MOCK_SLIDES_CREATED_AT,
}: SlidesViewerProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const total = MOCK_SLIDES.length;
  const slide = MOCK_SLIDES[currentIndex];

  if (!slide) return null;

  return (
    <div className="flex h-full flex-col">
      {/* Header: serif title, metadata, .pdf / .pptx buttons */}
      <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div className="min-w-0 flex-1 pr-4">
          <h2 className="font-serif text-[26px] font-semibold leading-tight text-foreground">
            {title}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            slides · {createdAt}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm">
            <Download className="h-3.5 w-3.5" />
            .pdf
          </Button>
          <Button variant="outline" size="sm">
            <Download className="h-3.5 w-3.5" />
            .pptx
          </Button>
        </div>
      </div>

      {/* Slide display — always dark, 16:9 */}
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <div
          className="w-full max-w-3xl overflow-hidden rounded-xl shadow-md"
          style={{ aspectRatio: "16 / 9" }}
        >
          {/* Dark slide — намеренно dark независимо от темы приложения (slides viewer design, T6c) */}
          <div
            className="flex h-full flex-col p-10"
            style={{
              backgroundColor: "var(--slides-bg)",
              color: "var(--slides-fg)",
            }}
          >
            {/* Orb logo */}
            <div className="flex items-center gap-2" style={{ opacity: 0.5 }}>
              <SphereOrb size={16} />
              <span
                className="font-mono text-[10px] tracking-widest uppercase"
                style={{ color: "var(--slides-fg)" }}
              >
                LearnFlowAI
              </span>
            </div>

            {/* Content */}
            <div className="flex flex-1 flex-col justify-center gap-3">
              <h2
                className="font-serif text-[44px] font-semibold leading-tight"
                style={{ color: "var(--slides-fg)" }}
              >
                {slide.title}
              </h2>
              <p
                className="whitespace-pre-line text-lg leading-relaxed"
                style={{ color: "var(--slides-fg)", opacity: 0.72 }}
              >
                {slide.body}
              </p>
            </div>

            {/* Footer */}
            <p
              className="font-mono text-[10px] tracking-wide"
              style={{ color: "var(--slides-fg)", opacity: 0.35 }}
            >
              {currentIndex + 1} / {total}
            </p>
          </div>
        </div>
      </div>

      {/* Thumbnails + navigation */}
      <div className="shrink-0 border-t border-border px-6 py-3">
        <div className="flex items-center gap-4">
          {/* Thumbnail strip — horizontal scroll */}
          <div className="flex flex-1 gap-2 overflow-x-auto pb-1">
            {MOCK_SLIDES.map((s, i) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setCurrentIndex(i)}
                className={cn(
                  "shrink-0 cursor-pointer overflow-hidden rounded transition-all",
                  i === currentIndex
                    ? "ring-2 ring-ring ring-offset-1 ring-offset-background"
                    : "opacity-60 ring-1 ring-border hover:opacity-90",
                )}
                style={{ width: 86, height: 50 }}
              >
                <div
                  className="flex h-full flex-col p-1.5"
                  style={{ backgroundColor: "var(--slides-bg)" }}
                >
                  <p
                    className="truncate text-left font-mono text-[6px] leading-tight"
                    style={{ color: "var(--slides-fg)", opacity: 0.7 }}
                  >
                    {s.title}
                  </p>
                </div>
              </button>
            ))}
          </div>

          {/* Navigation */}
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
              disabled={currentIndex === 0}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-[4rem] text-center font-mono text-sm text-muted-foreground">
              {currentIndex + 1} / {total}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => setCurrentIndex((i) => Math.min(total - 1, i + 1))}
              disabled={currentIndex === total - 1}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
