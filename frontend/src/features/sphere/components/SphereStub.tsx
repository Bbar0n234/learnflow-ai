import { useParams } from "react-router";

export function SphereStub() {
  const { id } = useParams();

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Knowledge Sphere</h2>
      <p className="text-muted-foreground">
        Project <code className="rounded bg-muted px-1.5 py-0.5">{id}</code> —
        knowledge sphere will appear here.
      </p>
    </div>
  );
}
