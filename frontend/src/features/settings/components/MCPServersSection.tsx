import { useState } from "react";
import { Pencil, Plug, Plus, Trash2, Zap } from "lucide-react";
import { useMCPServers } from "../hooks/useMCPServers";
import { useMCPServerMutations } from "../hooks/useMCPServerMutations";
import { MCPServerForm } from "./MCPServerForm";
import { Button } from "@/shared/ui/button";
import { Switch } from "@/shared/ui/switch";
import type {
  MCPServer,
  MCPServerCreate,
  MCPServerUpdate,
} from "@/shared/api/types";

interface Props {
  scope: "user" | "project" | "thread";
  projectId?: string;
  threadId?: string;
}

export function MCPServersSection({ scope, projectId, threadId }: Props) {
  const { data, isLoading } = useMCPServers(scope, projectId, threadId);
  const { create, update, remove, test, toggle } = useMCPServerMutations(
    scope,
    projectId,
    threadId,
  );
  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null);
  const [testResults, setTestResults] = useState<Record<string, string>>({});

  const servers = data?.items ?? [];
  const inherited = data?.inherited ?? [];

  const handleCreate = (body: MCPServerCreate) => {
    create.mutate(body, {
      onSuccess: () => setShowForm(false),
    });
  };

  const handleUpdate = (body: MCPServerCreate) => {
    if (!editingServer) return;
    const updateBody: MCPServerUpdate = { ...body };
    update.mutate(
      { id: editingServer.id, body: updateBody },
      { onSuccess: () => setEditingServer(null) },
    );
  };

  const handleTest = (id: string) => {
    setTestResults((prev) => ({ ...prev, [id]: "testing..." }));
    test.mutate(id, {
      onSuccess: (result) => {
        setTestResults((prev) => ({
          ...prev,
          [id]: result.success
            ? `OK (${result.tools.length} tools)`
            : `Failed: ${result.error}`,
        }));
      },
      onError: () => {
        setTestResults((prev) => ({
          ...prev,
          [id]: "Connection failed",
        }));
      },
    });
  };

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <label className="text-sm font-medium">MCP Servers</label>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setShowForm(!showForm);
            setEditingServer(null);
          }}
          disabled={servers.length >= 5}
        >
          <Plus className="mr-1 h-4 w-4" />
          Add
        </Button>
      </div>

      {showForm && !editingServer && (
        <div className="mb-4 rounded-md border border-border p-3">
          <MCPServerForm
            onSubmit={handleCreate}
            onCancel={() => setShowForm(false)}
            isPending={create.isPending}
            error={create.error}
          />
        </div>
      )}

      {editingServer && (
        <div className="mb-4 rounded-md border border-border p-3">
          <MCPServerForm
            onSubmit={handleUpdate}
            onCancel={() => setEditingServer(null)}
            isPending={update.isPending}
            error={update.error}
            initialData={editingServer}
          />
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <>
          {inherited.length > 0 && (
            <div className="mb-3 space-y-2">
              {inherited.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-3 rounded-md border border-border p-3 opacity-90"
                >
                  <Plug className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{s.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.transport} &middot; {s.url}
                    </p>
                  </div>
                  <Switch
                    checked={!s.is_disabled}
                    onCheckedChange={(checked) =>
                      toggle.mutate({ id: s.id, disabled: !checked })
                    }
                  />
                </div>
              ))}
              {servers.length > 0 && (
                <div className="my-2 border-t border-border" />
              )}
            </div>
          )}

          {servers.length === 0 && inherited.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No MCP servers configured.
            </p>
          ) : (
            <div className="space-y-2">
              {servers.map((s) => (
                <div
                  key={s.id}
                  className="flex items-center gap-3 rounded-md border border-border p-3"
                >
                  <Plug className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{s.name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {s.transport} &middot; {s.url}
                      {s.api_key_hint
                        ? ` (${s.api_key_hint})`
                        : s.has_api_key
                          ? " (key set)"
                          : ""}
                    </p>
                    {testResults[s.id] && (
                      <p className="text-xs text-muted-foreground">
                        {testResults[s.id]}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => handleTest(s.id)}
                    title="Test connection"
                  >
                    <Zap className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      setEditingServer(s);
                      setShowForm(false);
                    }}
                    title="Edit"
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => remove.mutate(s.id)}
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
