import { useParams } from "react-router";

export function ArtifactViewStub() {
  const { id, aid } = useParams();

  return (
    <div className="p-6">
      <h2 className="mb-2 text-lg font-semibold">Artifact</h2>
      <p className="text-muted-foreground">
        Project <code className="rounded bg-muted px-1.5 py-0.5">{id}</code>,
        Artifact <code className="rounded bg-muted px-1.5 py-0.5">{aid}</code>
      </p>
    </div>
  );
}
