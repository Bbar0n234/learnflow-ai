import { useParams } from "react-router";
import { Download, Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { useArtifact } from "@/shared/api/artifacts";
import { downloadArtifact } from "@/shared/api/artifacts";

export function ArtifactView() {
  const { id, aid } = useParams();
  const { data, isLoading, isError } = useArtifact(id, aid);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Загрузка артефакта…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-destructive">
        Не удалось загрузить артефакт.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header: serif title 26px + metadata + action buttons */}
      <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div className="min-w-0 flex-1 pr-4">
          <h2 className="font-serif text-[26px] font-semibold leading-tight text-foreground">
            {data?.title}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {data?.type}
            {" · "}
            {data && new Date(data.created_at).toLocaleDateString("ru-RU")}
          </p>
        </div>

        {/* Action buttons: Редактировать (outline-акцент) | .md (primary) | .pdf (outline) */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Редактировать — visual stub, editing via T6c */}
          <Button
            variant="outline"
            size="sm"
            disabled
            className="border-ring/60 text-ring disabled:opacity-50"
          >
            <Pencil className="h-3.5 w-3.5" />
            Редактировать
          </Button>

          {/* .md download — primary */}
          <Button
            size="sm"
            onClick={() => void downloadArtifact(id!, aid!, "md")}
          >
            <Download className="h-3.5 w-3.5" />
            .md
          </Button>

          {/* .pdf download — outline */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => void downloadArtifact(id!, aid!, "pdf")}
          >
            <Download className="h-3.5 w-3.5" />
            .pdf
          </Button>
        </div>
      </div>

      {/* Content in card */}
      <ScrollArea className="min-h-0 flex-1 p-6">
        {data?.content ? (
          <div className="rounded-xl border border-border bg-card px-8 py-6">
            <div className="sphere-prose">
              <MarkdownRenderer>{data.content}</MarkdownRenderer>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Содержимое недоступно.
          </p>
        )}
      </ScrollArea>
    </div>
  );
}
