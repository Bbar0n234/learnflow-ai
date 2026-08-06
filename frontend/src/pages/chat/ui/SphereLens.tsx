import { useEffect } from "react";
import { X } from "lucide-react";
import { cn } from "@/shared/lib/utils";

// ── Mock data (stub, no backend) ──────────────────────────────────────────────
const MOCK_VERSION_HISTORY = [
  {
    semver: "v2.4.1",
    summary: "Патч: уточнён JTBD и ценностное предложение",
    author: "агент",
    ts: "сегодня, 14:32",
  },
  {
    semver: "v2.4.0",
    summary: "Минор: добавлена целевая аудитория",
    author: "вы",
    ts: "вчера, 10:15",
  },
  {
    semver: "v2.3.0",
    summary: "Минор: ключевые принципы",
    author: "агент",
    ts: "2 дня назад",
  },
  {
    semver: "v2.2.0",
    summary: "Патч: правка концепции",
    author: "вы",
    ts: "5 дней назад",
  },
];

interface SphereLensProps {
  open: boolean;
  onClose: () => void;
}

export function SphereLens({ open, onClose }: SphereLensProps) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      {/* Scrim */}
      <div
        className="fixed inset-0 z-40"
        style={{ background: "var(--scrim-overlay)" }}
        onClick={onClose}
        aria-hidden={true}
      />
      {/* Modal */}
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-6"
        role="dialog"
        aria-modal={true}
        aria-label="Линза сферы"
      >
        <div
          className="flex max-h-[90vh] max-w-[95vw] overflow-hidden rounded-2xl border border-border bg-card"
          style={{
            width: 920,
            height: 620,
            boxShadow: "var(--shadow-lens)",
          }}
        >
          {/* Main content area */}
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
            {/* Header */}
            <div className="flex h-[52px] shrink-0 items-center gap-3 border-b border-border px-5">
              <span className="font-serif text-sm font-semibold text-foreground">
                Сфера знаний
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">
                v2.4.1
              </span>
              <div className="flex-1" />
              <button
                onClick={onClose}
                className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                aria-label="Закрыть"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            {/* Document */}
            <div className="sphere-prose flex-1 overflow-auto px-8 py-6 text-sm">
              <h2>Концепция продукта</h2>
              <p>
                LearnFlowAI — образовательная платформа для самостоятельного
                обучения. Агент помогает структурировать знания, создавать
                артефакты и отслеживать прогресс.
              </p>
              <h2>Ключевые принципы</h2>
              <ul>
                <li>Непрерывность контекста: агент помнит всё обсуждённое.</li>
                <li>Структурированные знания: Сфера хранит ключевые тезисы.</li>
                <li>Активное обучение: флэшкарты, тесты, конспекты.</li>
              </ul>
              <h2>Целевая аудитория</h2>
              <p>
                {/* Highlighted fragment — the text that triggered the lens open */}
                <span className="rounded bg-secondary px-1 text-secondary-foreground">
                  Студенты и специалисты, стремящиеся учиться эффективнее.
                </span>{" "}
                Платформа ориентирована на людей, которым важно сохранять и
                структурировать знания в процессе обучения.
              </p>
            </div>
          </div>

          {/* Version history rail */}
          <div className="flex w-[252px] shrink-0 flex-col border-l border-border">
            <div className="flex h-[52px] shrink-0 items-center border-b border-border px-4">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                История версий
              </span>
            </div>
            <div className="flex-1 overflow-auto">
              {MOCK_VERSION_HISTORY.map((v, i) => (
                <div
                  key={v.semver}
                  className={cn(
                    "border-b border-border px-4 py-3 transition-colors hover:bg-muted cursor-pointer",
                    i === 0 && "bg-secondary/30",
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] font-medium text-primary">
                      {v.semver}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {v.author}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
                    {v.summary}
                  </p>
                  <p className="mt-1 text-[10px] text-muted-foreground/60">
                    {v.ts}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
