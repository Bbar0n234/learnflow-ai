import { Link, useParams } from "react-router";
import { FileText } from "lucide-react";
import { useArtifacts } from "../hooks/useArtifacts";

export function ArtifactList() {
  const { id } = useParams();
  const { data, isLoading, isError } = useArtifacts(id);

  return (
    <div className="h-full overflow-auto p-6">
      <h2 className="mb-4 text-lg font-semibold">Artifacts</h2>

      {isLoading && (
        <p className="text-muted-foreground">Loading artifacts...</p>
      )}
      {isError && <p className="text-destructive">Failed to load artifacts.</p>}
      {data && data.items.length === 0 && (
        <p className="text-muted-foreground">
          No artifacts yet. They will appear here as the AI generates them.
        </p>
      )}
      {data && data.items.length > 0 && (
        <div className="flex flex-col gap-1">
          {data.items.map((artifact) => (
            <Link
              key={artifact.id}
              to={`/projects/${id}/artifacts/${artifact.id}`}
              className="flex items-center gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-muted"
            >
              <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{artifact.title}</p>
                <p className="text-xs text-muted-foreground">
                  {artifact.type} &middot;{" "}
                  {new Date(artifact.created_at).toLocaleDateString()}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
