import { Link, useParams } from "react-router";
import { ArrowLeft, Download } from "lucide-react";
import { Button, buttonVariants } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/components/MarkdownRenderer";
import { useArtifact } from "../hooks/useArtifact";
import { downloadArtifact } from "@/shared/api/artifacts";

export function ArtifactView() {
  const { id, aid } = useParams();
  const { data, isLoading, isError } = useArtifact(id, aid);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Loading artifact...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-destructive">
        Failed to load artifact.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-3">
          <Link
            to={`/projects/${id}/artifacts`}
            className={buttonVariants({ variant: "ghost", size: "icon" })}
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div>
            <h2 className="text-lg font-semibold">{data?.title}</h2>
            <p className="text-xs text-muted-foreground">
              {data?.type} &middot;{" "}
              {data && new Date(data.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void downloadArtifact(id!, aid!, "md")}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            MD
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void downloadArtifact(id!, aid!, "pdf")}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            PDF
          </Button>
        </div>
      </div>
      <ScrollArea className="flex-1 px-6 py-4">
        {data?.content ? (
          <MarkdownRenderer>{data.content}</MarkdownRenderer>
        ) : (
          <p className="text-muted-foreground">No content available.</p>
        )}
      </ScrollArea>
    </div>
  );
}
