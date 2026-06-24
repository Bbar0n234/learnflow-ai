import { useState } from "react";
import { Download, Play, Pause } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";
import {
  MOCK_AUDIO_TITLE,
  MOCK_AUDIO_CREATED_AT,
  MOCK_AUDIO_DURATION_SECONDS,
  MOCK_AUDIO_SUMMARY,
  MOCK_AUDIO_TRANSCRIPT,
  MOCK_AUDIO_NOTES,
  MOCK_KEY_MOMENTS,
} from "../model/mock-artifact-data";

interface AudioViewerProps {
  title?: string;
  createdAt?: string;
}

type AudioTab = "summary" | "transcript" | "notes";

const TAB_LABELS: Record<AudioTab, string> = {
  summary: "Саммари",
  transcript: "Транскрипт",
  notes: "Заметки агента",
};

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString()}:${s.toString().padStart(2, "0")}`;
}

export function AudioViewer({
  title = MOCK_AUDIO_TITLE,
  createdAt = MOCK_AUDIO_CREATED_AT,
}: AudioViewerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [speedIndex, setSpeedIndex] = useState(4); // 1.5× default
  const [activeTab, setActiveTab] = useState<AudioTab>("summary");

  const total = MOCK_AUDIO_DURATION_SECONDS;
  const speed = SPEEDS[speedIndex];

  function seekTo(timeSeconds: number) {
    setCurrentTime(timeSeconds);
    setIsPlaying(true);
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
            audio · {createdAt}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button size="sm">
            <Download className="h-3.5 w-3.5" />
            .mp3
          </Button>
        </div>
      </div>

      {/* Player */}
      <div className="shrink-0 border-b border-border px-6 py-4">
        <div className="flex items-center gap-4">
          {/* Play/Pause circle 40px primary */}
          <button
            type="button"
            onClick={() => setIsPlaying((p) => !p)}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition-all hover:opacity-90 active:scale-95"
          >
            {isPlaying ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="ml-0.5 h-4 w-4" />
            )}
          </button>

          {/* Progress bar 5px */}
          <div className="flex flex-1 flex-col gap-1">
            <input
              type="range"
              min={0}
              max={total}
              value={currentTime}
              onChange={(e) => setCurrentTime(Number(e.target.value))}
              className="h-[5px] w-full cursor-pointer appearance-none rounded-full bg-border [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
            />
            <div className="flex justify-between font-mono text-[11px] text-muted-foreground">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(total)}</span>
            </div>
          </div>

          {/* Speed cycle */}
          <button
            type="button"
            onClick={() => setSpeedIndex((i) => (i + 1) % SPEEDS.length)}
            className="shrink-0 rounded-md border border-border px-2 py-1 font-mono text-xs text-foreground transition-colors hover:bg-muted"
          >
            {speed}×
          </button>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex shrink-0 border-b border-border px-6">
        {(Object.keys(TAB_LABELS) as AudioTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={cn(
              "px-3 py-2.5 text-sm font-medium transition-colors",
              activeTab === tab
                ? "text-primary [box-shadow:inset_0_-2px_0_var(--ring)]"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === "summary" && (
          <div className="space-y-5 p-6">
            <p className="max-w-[680px] text-sm leading-relaxed text-foreground">
              {MOCK_AUDIO_SUMMARY}
            </p>
            <div>
              <h3 className="mb-2 font-serif text-base font-semibold text-foreground">
                Ключевые моменты
              </h3>
              <div className="space-y-0.5">
                {MOCK_KEY_MOMENTS.map((m) => (
                  <button
                    key={m.timeLabel}
                    type="button"
                    onClick={() => seekTo(m.timeSeconds)}
                    className="flex w-full max-w-[680px] items-center gap-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-muted"
                  >
                    <span className="shrink-0 font-mono text-xs text-ring">
                      {m.timeLabel}
                    </span>
                    <span className="text-sm text-foreground">
                      {m.description}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
        {activeTab === "transcript" && (
          <div className="p-6">
            <pre className="max-w-[680px] whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground">
              {MOCK_AUDIO_TRANSCRIPT}
            </pre>
          </div>
        )}
        {activeTab === "notes" && (
          <div className="p-6">
            <pre className="max-w-[680px] whitespace-pre-wrap text-sm leading-relaxed text-foreground">
              {MOCK_AUDIO_NOTES}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
