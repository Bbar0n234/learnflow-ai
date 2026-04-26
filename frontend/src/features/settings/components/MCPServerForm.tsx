import { useState } from "react";
import { Button } from "@/shared/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import type { MCPServer, MCPServerCreate } from "@/shared/api/types";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";

interface Props {
  onSubmit: (data: MCPServerCreate) => void;
  onCancel: () => void;
  isPending: boolean;
  error: unknown;
  initialData?: MCPServer;
}

export function MCPServerForm({
  onSubmit,
  onCancel,
  isPending,
  error,
  initialData,
}: Props) {
  const isEdit = !!initialData;
  const [name, setName] = useState(initialData?.name ?? "");
  const [transport, setTransport] = useState<"http" | "sse">(
    (initialData?.transport as "http" | "sse") ?? "http",
  );
  const [url, setUrl] = useState(initialData?.url ?? "");
  const [apiKey, setApiKey] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data: MCPServerCreate = { name, transport, url };
    if (apiKey) {
      data.api_key = apiKey;
    } else if (isEdit && apiKey === "") {
      // empty string = keep current key in edit mode (don't send api_key)
    }
    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium">Name</label>
        <input
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={100}
          placeholder="my-server"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium">Transport</label>
        <Select
          value={transport}
          onValueChange={(v) => setTransport(v as "http" | "sse")}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="http">HTTP (Streamable)</SelectItem>
            <SelectItem value="sse">SSE</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium">URL</label>
        <input
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://mcp.example.com/v1"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium">
          API Key {isEdit ? "(leave empty to keep current)" : "(optional)"}
        </label>
        <input
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={
            isEdit && initialData?.api_key_hint
              ? `Current: ${initialData.api_key_hint}`
              : "Bearer token"
          }
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={isPending}>
          {isPending
            ? isEdit
              ? "Saving..."
              : "Adding..."
            : isEdit
              ? "Save"
              : "Add Server"}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {isSecurityViolation(error) && (
        <p className="text-sm text-destructive">{SECURITY_VIOLATION_MESSAGE}</p>
      )}
    </form>
  );
}
