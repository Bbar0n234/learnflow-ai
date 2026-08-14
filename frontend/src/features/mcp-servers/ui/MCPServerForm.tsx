import { useState } from "react";
import { Button } from "@/shared/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import type { MCPServer, MCPServerCreate } from "@/shared/api/mcp-servers";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";
import { getApiErrorMessage } from "@/shared/lib/api-error";

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
        <label htmlFor="mcp-name" className="mb-1 block text-xs font-medium">
          Название
        </label>
        <input
          id="mcp-name"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={100}
          placeholder="my-server"
        />
      </div>
      <div>
        <label
          id="mcp-transport-label"
          className="mb-1 block text-xs font-medium"
        >
          Транспорт
        </label>
        <Select
          value={transport}
          onValueChange={(v) => setTransport(v as "http" | "sse")}
        >
          <SelectTrigger
            className="w-full"
            aria-labelledby="mcp-transport-label"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="http">HTTP (Streamable)</SelectItem>
            <SelectItem value="sse">SSE</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <label htmlFor="mcp-url" className="mb-1 block text-xs font-medium">
          URL
        </label>
        <input
          id="mcp-url"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          placeholder="https://mcp.example.com/v1"
        />
      </div>
      <div>
        <label htmlFor="mcp-api-key" className="mb-1 block text-xs font-medium">
          API-ключ{" "}
          {isEdit ? "(оставьте пустым, чтобы не менять)" : "(необязательно)"}
        </label>
        <input
          id="mcp-api-key"
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={
            isEdit && initialData?.api_key_hint
              ? `Сейчас: ${initialData.api_key_hint}`
              : "Токен доступа"
          }
        />
      </div>
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={isPending}>
          {isPending
            ? isEdit
              ? "Сохраняем…"
              : "Добавляем…"
            : isEdit
              ? "Сохранить"
              : "Добавить сервер"}
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={onCancel}>
          Отмена
        </Button>
      </div>
      {isSecurityViolation(error) ? (
        <p className="text-sm text-destructive">{SECURITY_VIOLATION_MESSAGE}</p>
      ) : error ? (
        <p className="text-sm text-destructive">{getApiErrorMessage(error)}</p>
      ) : null}
    </form>
  );
}
