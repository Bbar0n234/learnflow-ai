import { Link } from "react-router";
import { FileText } from "lucide-react";

interface ArtifactCardProps {
  artifact: { id: string; title: string; type: string };
  projectId: string;
}

export function ArtifactCard({ artifact, projectId }: ArtifactCardProps) {
  return (
    <Link
      to={`/projects/${projectId}/artifacts/${artifact.id}`}
      className="mt-2 flex items-center gap-3 rounded-md border border-border bg-card p-3 transition-colors hover:bg-accent"
    >
      <FileText className="h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{artifact.title}</p>
        <p className="text-xs text-muted-foreground">
          {artifact.type}
        </p>
      </div>
    </Link>
  );
}
