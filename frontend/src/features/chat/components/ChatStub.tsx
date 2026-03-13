import { useParams } from "react-router";

export function ChatStub() {
  const { id, cid } = useParams();

  return (
    <div>
      <h2 className="mb-2 text-lg font-semibold">Chat</h2>
      <p className="text-muted-foreground">
        Project <code className="rounded bg-muted px-1.5 py-0.5">{id}</code>,
        Chat <code className="rounded bg-muted px-1.5 py-0.5">{cid}</code>
      </p>
    </div>
  );
}
