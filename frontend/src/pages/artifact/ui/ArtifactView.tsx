import { useParams, useSearchParams } from "react-router";
import { Download, Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { LoadingState, StateScreen } from "@/shared/ui/StateScreen";
import {
  useArtifact,
  downloadArtifact,
  isArtifactNotFound,
} from "@/shared/api/artifacts";
import { getArtifactCategory } from "@/shared/lib/artifact-category";
import { ImageViewer } from "./ImageViewer";

export function ArtifactView() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const path = searchParams.get("path") ?? undefined;
  const { data, isLoading, isError, error, refetch } = useArtifact(id, path);

  if (isLoading) {
    return <LoadingState className="h-full" label="Загрузка артефакта…" />;
  }

  if (isError) {
    // Путь-идентичность перезаписываема и переименовываема (ADR-032):
    // 404 — не ошибка загрузки, а легитимное «файла по этой ссылке больше
    // нет» (переименован/удалён агентом, ссылка из истории устарела).
    // Сетевая/5xx-ошибка — отдельная, обычная ветка.
    if (isArtifactNotFound(error)) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-sm text-foreground">Файл больше не существует</p>
          <p className="max-w-sm break-all font-mono text-xs text-muted-foreground">
            {path}
          </p>
          <p className="max-w-sm text-xs text-muted-foreground">
            Он мог быть переименован или удалён агентом — ссылка из истории
            устарела.
          </p>
        </div>
      );
    }
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

  const formattedDate = data?.updated_at
    ? new Date(data.updated_at).toLocaleDateString("ru-RU")
    : undefined;
  const category = data
    ? getArtifactCategory(data.type, data.content !== undefined)
    : undefined;

  if (category === "image") {
    return (
      <ImageViewer
        projectId={id}
        path={path}
        title={data?.title}
        type={data?.type}
        updatedAt={formattedDate}
      />
    );
  }

  if (category === "binary") {
    return (
      <div className="flex h-full flex-col">
        <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
          <div className="min-w-0 flex-1 pr-4">
            <h2 className="font-serif text-[26px] font-semibold leading-tight text-foreground">
              {data?.title}
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              {data?.type}
              {" · изменён "}
              {formattedDate}
            </p>
          </div>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-sm text-muted-foreground">
          <p>Предпросмотр недоступен — бинарный файл.</p>
          <Button size="sm" onClick={() => void downloadArtifact(id!, path!)}>
            <Download className="h-3.5 w-3.5" />
            Скачать
          </Button>
        </div>
      </div>
    );
  }

  // markdown / text — общий вьюер, различие только в рендере content
  // (markdown через MarkdownRenderer, нераспознанное текстовое расширение —
  // моно-рендером). Кнопка `.pdf` снята (C3, export не поддерживается);
  // скачивание — по фактическому расширению файла, не жёстко `.md`.
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-start justify-between border-b border-border px-6 py-4">
        <div className="min-w-0 flex-1 pr-4">
          <h2 className="font-serif text-[26px] font-semibold leading-tight text-foreground">
            {data?.title}
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {data?.type}
            {" · изменён "}
            {formattedDate}
          </p>
        </div>

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

          <Button size="sm" onClick={() => void downloadArtifact(id!, path!)}>
            <Download className="h-3.5 w-3.5" />.{data?.type}
          </Button>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1 p-6">
        {data?.content ? (
          <div className="rounded-xl border border-border bg-card px-8 py-6">
            {category === "markdown" ? (
              <div className="sphere-prose">
                <MarkdownRenderer>{data.content}</MarkdownRenderer>
              </div>
            ) : (
              <pre className="whitespace-pre-wrap font-mono text-sm text-foreground">
                {data.content}
              </pre>
            )}
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
