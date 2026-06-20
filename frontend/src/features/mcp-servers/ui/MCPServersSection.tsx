import { useState } from "react";
import { Pencil, Plus, Trash2, Zap } from "lucide-react";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { useMCPServers } from "@/shared/api/mcp-servers";
import { useMCPServerMutations } from "@/shared/api/mcp-servers";
import { MCPServerForm } from "./MCPServerForm";
import { Button } from "@/shared/ui/button";
import { Switch } from "@/shared/ui/switch";
import type {
  MCPServer,
  InheritedMCPServer,
  MCPServerCreate,
  MCPServerUpdate,
} from "@/shared/api/mcp-servers";

interface Props {
  scope: "user" | "project" | "thread";
  projectId?: string;
  threadId?: string;
}

function StatusDot({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={`h-2 w-2 shrink-0 rounded-full ${
        enabled ? "bg-mcp-connected" : "bg-mcp-disabled"
      }`}
    />
  );
}

function OwnedServerRow({
  server,
  onEdit,
  onDelete,
  onTest,
  testResult,
}: {
  server: MCPServer;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  testResult?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
      <StatusDot enabled={server.is_active} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{server.name}</p>
        <p className="truncate font-mono text-[10px] text-muted-foreground">
          {server.transport} · {server.url}
          {server.api_key_hint
            ? ` (${server.api_key_hint})`
            : server.has_api_key
              ? " (key set)"
              : ""}
        </p>
        {testResult && (
          <p className="text-[10px] text-muted-foreground">{testResult}</p>
        )}
      </div>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onTest}
        title="Проверить соединение"
      >
        <Zap className="h-3.5 w-3.5" />
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onEdit}
        title="Редактировать"
      >
        <Pencil className="h-3.5 w-3.5" />
      </Button>
      <Button variant="ghost" size="icon-sm" onClick={onDelete} title="Удалить">
        <Trash2 className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

function InheritedServerRow({
  server,
  onToggle,
  onTest,
  testResult,
}: {
  server: InheritedMCPServer;
  onToggle: (enabled: boolean) => void;
  onTest: () => void;
  testResult?: string;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-background px-3 py-2.5 opacity-90">
      <StatusDot enabled={!server.is_disabled} />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-foreground">{server.name}</p>
        <p className="truncate font-mono text-[10px] text-muted-foreground">
          {server.transport} · {server.url}
        </p>
        {testResult && (
          <p className="text-[10px] text-muted-foreground">{testResult}</p>
        )}
      </div>
      <Switch
        checked={!server.is_disabled}
        onCheckedChange={(checked) => onToggle(checked)}
      />
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onTest}
        title="Проверить соединение"
      >
        <Zap className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
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
    setTestResults((prev) => ({ ...prev, [id]: "Проверяем…" }));
    test.mutate(id, {
      onSuccess: (result) => {
        setTestResults((prev) => ({
          ...prev,
          [id]: result.success
            ? `OK (${result.tools.length} инструментов)`
            : `Ошибка: ${result.error}`,
        }));
      },
      onError: (err) => {
        setTestResults((prev) => ({
          ...prev,
          [id]: getApiErrorMessage(err),
        }));
      },
    });
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">
          MCP-серверы
        </label>
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
          Добавить
        </Button>
      </div>

      {showForm && !editingServer && (
        <div className="mb-4 rounded-lg border border-border bg-background p-3">
          <MCPServerForm
            onSubmit={handleCreate}
            onCancel={() => setShowForm(false)}
            isPending={create.isPending}
            error={create.error}
          />
        </div>
      )}

      {editingServer && (
        <div className="mb-4 rounded-lg border border-border bg-background p-3">
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
        <p className="text-sm text-muted-foreground">Загрузка…</p>
      ) : (
        <>
          {inherited.length > 0 && (
            <div className="mb-3 space-y-1.5">
              {inherited.map((s) => (
                <InheritedServerRow
                  key={s.id}
                  server={s}
                  onTest={() => handleTest(s.id)}
                  onToggle={(checked) =>
                    toggle.mutate({ id: s.id, disabled: !checked })
                  }
                  testResult={testResults[s.id]}
                />
              ))}
              {servers.length > 0 && (
                <div className="my-2 border-t border-border" />
              )}
            </div>
          )}

          {servers.length === 0 && inherited.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              MCP-серверы не настроены.
            </p>
          ) : (
            <div className="space-y-1.5">
              {servers.map((s) => (
                <OwnedServerRow
                  key={s.id}
                  server={s}
                  onEdit={() => {
                    setEditingServer(s);
                    setShowForm(false);
                  }}
                  onDelete={() => remove.mutate(s.id)}
                  onTest={() => handleTest(s.id)}
                  testResult={testResults[s.id]}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
