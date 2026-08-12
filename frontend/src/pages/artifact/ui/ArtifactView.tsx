import { useParams } from "react-router";
import { Download, Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { LoadingState, StateScreen } from "@/shared/ui/StateScreen";
import { useArtifact } from "@/shared/api/artifacts";
import { downloadArtifact } from "@/shared/api/artifacts";
import { SlidesViewer } from "./SlidesViewer";
import { ImageViewer } from "./ImageViewer";
import { AudioViewer } from "./AudioViewer";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

export function ArtifactView() {
  const { id, aid } = useParams();
  const { data, isLoading, isError, refetch } = useArtifact(id, aid);

  if (isLoading) {
    return <LoadingState className="h-full" label="Загрузка артефакта…" />;
  }

  if (isError) {
    return (
      <StateScreen
        scene="error-state"
        alt="Иллюстрация: ошибка"
        illustrationClassName="max-w-[280px]"
        title="Не удалось загрузить артефакт"
        description="Что-то пошло не так при загрузке. Проверьте соединение и попробуйте ещё раз."
        action={
          <Button variant="outline" onClick={() => void refetch()}>
            Повторить
          </Button>
        }
        className="h-full"
      />
    );
  }

  // Type-based dispatch. slides/audio — T6c viewers (group B, mock data, no
  // backend contract), за фиче-флагом: в прод-сборке эти типы падают в
  // дефолтный markdown-viewer, т.к. тело (слайды/аудио) пока берётся из моков.
  // image (feat-010, трек T1) — реальный бэкенд-контракт, вне флага.
  const type = data?.type ?? "";
  const formattedDate = data?.created_at
    ? new Date(data.created_at).toLocaleDateString("ru-RU")
    : undefined;

  if (SHOW_GROUP_B_STUBS && type === "slides") {
    return <SlidesViewer title={data?.title} createdAt={formattedDate} />;
  }
  if (type === "image") {
    return (
      <ImageViewer
        projectId={id}
        artifactId={aid}
        title={data?.title}
        createdAt={formattedDate}
        content={data?.content}
      />
    );
  }
  if (SHOW_GROUP_B_STUBS && type === "audio") {
    return <AudioViewer title={data?.title} createdAt={formattedDate} />;
  }

  // Default: markdown viewer (group A, T4d)
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
