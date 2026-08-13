import { X, FileText, Mic, LayoutDashboard } from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { SphereOrb } from "@/shared/ui/SphereOrb";
import type { StudioControls, StudioTab } from "../model/useStudio";

// ── Mock data (stub, no backend) ──────────────────────────────────────────────
const MOCK_ARTIFACTS = [
  { id: "a-1", type: "md" as const, title: "Конспект лекции №1" },
  { id: "a-2", type: "slides" as const, title: "Презентация проекта" },
  { id: "a-3", type: "audio" as const, title: "Запись интервью" },
];

const ARTIFACT_PREVIEW: Record<string, string> = {
  "a-1":
    "Основные концепции платформы и архитектура знаний: агент как помощник, Сфера как память, артефакты как результаты.",
  "a-2": "Презентация из 12 слайдов: введение, технический стек, демо-сессия.",
  "a-3":
    "Интервью с пользователем (42 мин): ожидания, боли, желаемые результаты.",
};

// T2.2: ветка "image" снята — недостижимый мёртвый код (MOCK_ARTIFACTS
// никогда не заводил артефакт этого типа), а словарь категорий
// (shared/lib/artifact-category.ts) теперь единственное место, решающее
// "image" ли артефакт (§ Open Questions T2, OQ7).
function ArtifactTypeIcon({ type }: { type: "md" | "slides" | "audio" }) {
  switch (type) {
    case "slides":
      return <LayoutDashboard className="h-3.5 w-3.5" />;
    case "audio":
      return <Mic className="h-3.5 w-3.5" />;
    default:
      return <FileText className="h-3.5 w-3.5" />;
  }
}

function SegmentedToggle({
  tab,
  onChange,
}: {
  tab: StudioTab;
  onChange: (t: StudioTab) => void;
}) {
  return (
    <div className="flex flex-1 items-center rounded-full bg-bubble-user p-0.5">
      {(["sphere", "artifacts"] as const).map((t) => (
        <button
          key={t}
          onClick={() => onChange(t)}
          className={cn(
            "flex-1 rounded-full px-3 py-1 text-xs font-medium transition-all",
            tab === t
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {t === "sphere" ? "Сфера" : "Артефакты"}
        </button>
      ))}
    </div>
  );
}

function SpherePanelContent({ onOpenLens }: { onOpenLens: () => void }) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Orb + meta */}
      <div className="flex flex-col items-center gap-3 border-b border-border px-4 py-5">
        <SphereOrb size={80} showRings={false} showSparks />
        <div className="text-center">
          <p className="font-serif text-sm font-semibold text-foreground">
            Сфера знаний
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            v2.4.1 · 3 раздела · 12 записей
          </p>
        </div>
        <button
          onClick={onOpenLens}
          className="rounded-full bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/80"
        >
          Открыть в линзе
        </button>
      </div>
      {/* Content preview */}
      <div className="sphere-prose flex-1 overflow-auto px-5 py-4 text-sm">
        <h2>Концепция продукта</h2>
        <p>
          LearnFlowAI — образовательная платформа для самостоятельного обучения.
          Агент помогает структурировать знания и отслеживать прогресс.
        </p>
        <h2>Ключевые принципы</h2>
        <ul>
          <li>Непрерывность контекста</li>
          <li>Структурированные знания</li>
          <li>Активное обучение</li>
        </ul>
        <h2>Целевая аудитория</h2>
        <p>Студенты и специалисты, стремящиеся учиться эффективнее.</p>
      </div>
    </div>
  );
}

function ArtifactsPanelContent({ studio }: { studio: StudioControls }) {
  const activeId = studio.selectedArtifactId ?? "a-1";
  const selected = MOCK_ARTIFACTS.find((a) => a.id === activeId);

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Material chips */}
      <div className="flex flex-wrap gap-1.5 border-b border-border px-4 py-3">
        {MOCK_ARTIFACTS.map((a) => (
          <button
            key={a.id}
            onClick={() => studio.setSelectedArtifactId(a.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              activeId === a.id
                ? "bg-secondary text-secondary-foreground"
                : "bg-muted text-muted-foreground hover:bg-secondary/50 hover:text-secondary-foreground",
            )}
          >
            <ArtifactTypeIcon type={a.type} />
            {a.title}
          </button>
        ))}
      </div>
      {/* Mini-viewer */}
      <div className="flex-1 overflow-auto px-5 py-4">
        <p className="font-serif text-sm font-semibold text-foreground">
          {selected?.title ?? ""}
        </p>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
          {selected ? (ARTIFACT_PREVIEW[selected.id] ?? "") : ""}
        </p>
      </div>
      {/* Footer actions */}
      <div className="flex items-center gap-2 border-t border-border px-4 py-3">
        <button className="flex-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90">
          Открыть
        </button>
        {/* .pdf снята вместе с той же кнопкой во вьюере (C3, T2.2) —
            export в PDF не поддерживается. */}
        <button className="flex-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted">
          .md
        </button>
      </div>
    </div>
  );
}

interface StudioPanelProps {
  studio: StudioControls;
  onOpenLens: () => void;
}

export function StudioPanel({ studio, onOpenLens }: StudioPanelProps) {
  return (
    <aside className="flex h-full w-[470px] shrink-0 flex-col border-l border-border bg-muted">
      {/* Header */}
      <div className="flex h-[56px] shrink-0 items-center gap-3 border-b border-border px-4">
        <SegmentedToggle tab={studio.tab} onChange={studio.setTab} />
        <button
          onClick={studio.close}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-border hover:text-foreground"
          aria-label="Закрыть студию"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Body */}
      {studio.tab === "sphere" ? (
        <SpherePanelContent onOpenLens={onOpenLens} />
      ) : (
        <ArtifactsPanelContent studio={studio} />
      )}
    </aside>
  );
}
