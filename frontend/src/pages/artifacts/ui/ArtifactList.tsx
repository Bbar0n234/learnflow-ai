import { Link, useParams } from "react-router";
import { FileText, Image, Mic, LayoutDashboard } from "lucide-react";
import { Illustration } from "@/shared/ui/Illustration";
import { useArtifacts } from "@/shared/api/artifacts";
import { cn } from "@/shared/lib/utils";

/** Map artifact type string to a lucide icon element. */
function ArtifactIcon({ type }: { type: string }) {
  const cls = "h-[18px] w-[18px] shrink-0 text-muted-foreground";
  const t = type.toLowerCase();
  if (t === "image") return <Image className={cls} />;
  if (t === "audio") return <Mic className={cls} />;
  if (t === "slides") return <LayoutDashboard className={cls} />;
  return <FileText className={cls} />;
}

export function ArtifactList() {
  const { id, aid: selectedId } = useParams();
  const { data, isLoading, isError } = useArtifacts(id);

  return (
    <div className="flex h-full flex-col">
      {/* Panel header */}
      <div className="flex h-[56px] shrink-0 items-center border-b border-border px-4">
        <h2 className="font-serif text-base font-semibold text-foreground">
          Артефакты
        </h2>
      </div>

      {/* List body */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && (
          <p className="px-3 py-2 text-sm text-muted-foreground">Загрузка…</p>
        )}
        {isError && (
          <p className="px-3 py-2 text-sm text-destructive">
            Ошибка загрузки артефактов.
          </p>
        )}

        {data && data.items.length === 0 && (
          <div className="flex flex-col items-center gap-4 px-4 py-8">
            <Illustration
              scene="empty-artifacts"
              alt="No artifacts yet"
              className="w-full max-w-[200px]"
            />
            <p className="text-center text-sm text-muted-foreground">
              Артефактов пока нет. Они появятся по мере работы ИИ.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="flex flex-col gap-0.5">
            {data.items.map((artifact) => {
              const isSelected = artifact.id === selectedId;
              return (
                <Link
                  key={artifact.id}
                  to={`/projects/${id}/artifacts/${artifact.id}`}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
                    isSelected
                      ? "border border-secondary bg-secondary/30 [border-left-color:var(--ring)] [border-left-width:3px]"
                      : "hover:bg-muted",
                  )}
                >
                  {/* Type icon container — 36px */}
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
                    <ArtifactIcon type={artifact.type} />
                  </div>

                  {/* Title + date */}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {artifact.title}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(artifact.created_at).toLocaleDateString(
                        "ru-RU",
                      )}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
