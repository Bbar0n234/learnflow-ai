import { useParams } from "react-router";

export function ArtifactsStub() {
  const { id } = useParams();

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Artifacts</h2>
      <p className="text-muted-foreground">
        Project <code className="rounded bg-muted px-1.5 py-0.5">{id}</code> —
        artifacts list will appear here.
      </p>
    </div>
  );
}
