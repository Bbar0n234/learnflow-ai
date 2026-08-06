import { SphereOrb } from "@/shared/ui/SphereOrb";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { cn } from "@/shared/lib/utils";
import {
  type SphereVersionBump,
  MOCK_SPHERE_CURRENT_VERSION,
  MOCK_SPHERE_STATUS,
  MOCK_SPHERE_STATS,
  MOCK_SPHERE_HISTORY,
} from "../model/mock-sphere-version";

/**
 * Бейдж версии сферы.
 * Мажор — заливка primary; минор/патч — лаванда (secondary).
 */
function VersionBadge({
  version,
  bump,
}: {
  version: string;
  bump: SphereVersionBump;
}) {
  const isMajor = bump === "мажор";
  return (
    <span
      className={cn(
        "shrink-0 rounded-sm px-1.5 py-0.5 font-mono text-[10px] font-medium",
        isMajor
          ? "bg-primary text-primary-foreground"
          : "bg-secondary text-secondary-foreground",
      )}
    >
      {version}
    </span>
  );
}

/**
 * Правая панель «Жизнь сферы» — T6b семвер-UI (заглушка).
 * Содержит: орб 148px, счётчики, хронику обновлений, историю версий.
 * Все данные из mock — никаких сетевых вызовов (группа B, L0.5).
 */
export function SphereVersionPanel() {
  return (
    <aside className="flex w-[318px] shrink-0 flex-col border-l border-border bg-muted">
      <div className="flex h-[56px] shrink-0 items-center border-b border-border px-5">
        <h3 className="font-serif text-sm font-semibold text-foreground">
          Жизнь сферы
        </h3>
      </div>

      <ScrollArea className="flex-1">
        <div className="flex flex-col items-center gap-5 px-5 py-6">
          {/* Орб 148px с кольцами и искрами */}
          <SphereOrb size={148} />

          {/* Чип текущей версии + статус */}
          <div className="flex items-center gap-2">
            <span className="rounded-sm bg-secondary px-2 py-0.5 font-mono text-[11px] font-medium text-secondary-foreground">
              {MOCK_SPHERE_CURRENT_VERSION}
            </span>
            <span className="text-xs text-muted-foreground">
              · {MOCK_SPHERE_STATUS}
            </span>
          </div>

          {/* Счётчики: записи / связи / версии */}
          <div className="grid w-full grid-cols-3 gap-2">
            <div className="flex flex-col items-center gap-0.5 rounded-lg border border-border bg-card px-2 py-2.5">
              <span className="text-base font-semibold text-foreground">
                {MOCK_SPHERE_STATS.records}
              </span>
              <span className="text-[10px] text-muted-foreground">записей</span>
            </div>
            <div className="flex flex-col items-center gap-0.5 rounded-lg border border-border bg-card px-2 py-2.5">
              <span className="text-base font-semibold text-foreground">
                {MOCK_SPHERE_STATS.connections}
              </span>
              <span className="text-[10px] text-muted-foreground">связей</span>
            </div>
            <div className="flex flex-col items-center gap-0.5 rounded-lg border border-border bg-card px-2 py-2.5">
              <span className="text-base font-semibold text-foreground">
                {MOCK_SPHERE_STATS.versions}
              </span>
              <span className="text-[10px] text-muted-foreground">версий</span>
            </div>
          </div>

          {/* Разделитель */}
          <div className="w-full border-t border-border" />

          {/* Хроника обновлений */}
          <div className="w-full">
            <p className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Хроника
            </p>
            <div className="flex flex-col gap-3">
              {MOCK_SPHERE_HISTORY.slice(0, 4).map((entry) => (
                <div key={entry.version} className="flex items-start gap-2.5">
                  {/* Точка-маркер: акцент = новое, сирень = старое */}
                  <div
                    className={cn(
                      "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                      entry.isNew ? "bg-primary" : "bg-brand-lavender",
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs text-foreground">
                      {entry.summary}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {entry.timestamp} ·{" "}
                      {entry.author === "agent" ? "агент" : "вы"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Разделитель */}
          <div className="w-full border-t border-border" />

          {/* История версий */}
          <div className="w-full">
            <p className="mb-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              История версий
            </p>
            <div className="flex flex-col gap-2">
              {MOCK_SPHERE_HISTORY.map((entry) => (
                <div
                  key={entry.version}
                  className={cn(
                    "flex items-start gap-2.5 rounded-lg px-2.5 py-2",
                    entry.isNew && "bg-secondary/30",
                  )}
                >
                  <VersionBadge version={entry.version} bump={entry.bump} />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs leading-snug text-foreground">
                      {entry.summary}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {entry.timestamp} ·{" "}
                      {entry.author === "agent" ? "агент" : "вы"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </ScrollArea>
    </aside>
  );
}
