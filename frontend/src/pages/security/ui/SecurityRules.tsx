import { useState } from "react";
import {
  useRules,
  useCreateRule,
  useUpdateRule,
  useUpdateAnyRule,
  useDeleteRule,
  type CreateRuleInput,
} from "@/shared/api/security";
import { RuleForm } from "./RuleForm";
import { CorrelationRule } from "@/shared/api/security";
import { SecurityPagination } from "./SecurityPagination";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/shared/ui/dialog";
import { Plus, Edit2, Trash2 } from "lucide-react";
import { Switch } from "@/shared/ui/switch";
import { logger } from "@/shared/lib/logger";
import { getApiErrorMessage } from "@/shared/lib/api-error";

const RULE_TYPE_LABELS: Record<string, string> = {
  threshold: "Порог",
  sequence: "Последовательность",
  aggregate: "Агрегат",
};

export function SecurityRules() {
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [formOpen, setFormOpen] = useState(false);
  const [selectedRule, setSelectedRule] = useState<CorrelationRule | null>(
    null,
  );
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<number | null>(null);
  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [pendingToggleId, setPendingToggleId] = useState<number | null>(null);

  const { data, isLoading, error } = useRules(limit, offset);
  const createMutation = useCreateRule();
  const updateMutation = useUpdateRule(selectedRule?.id || 0);
  const toggleMutation = useUpdateAnyRule();
  const deleteMutation = useDeleteRule();

  const handleCreateNew = () => {
    setSelectedRule(null);
    setFormOpen(true);
  };

  const handleEdit = (rule: CorrelationRule) => {
    setSelectedRule(rule);
    setFormOpen(true);
  };

  const handleFormSubmit = async (input: CreateRuleInput) => {
    try {
      if (selectedRule) {
        await updateMutation.mutateAsync(input);
        setSuccessMessage("Правило обновлено");
      } else {
        await createMutation.mutateAsync(input);
        setSuccessMessage("Правило создано");
      }
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      logger.error("Form submit error", err);
      throw err;
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTargetId) return;
    try {
      await deleteMutation.mutateAsync(deleteTargetId);
      setSuccessMessage("Правило удалено");
      setDeleteConfirmOpen(false);
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      logger.error("Delete error", err);
    }
  };

  const handleToggleEnabled = async (
    rule: CorrelationRule,
    enabled: boolean,
  ) => {
    setErrorMessage("");
    setPendingToggleId(rule.id);
    try {
      await toggleMutation.mutateAsync({
        id: rule.id,
        input: { enabled },
      });
      setSuccessMessage(enabled ? "Правило включено" : "Правило выключено");
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      logger.error("Rule toggle error", err);
      setErrorMessage(getApiErrorMessage(err));
    } finally {
      setPendingToggleId(null);
    }
  };

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-destructive">
        Ошибка загрузки правил: {getApiErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {successMessage && (
        <div className="rounded-lg border border-border bg-muted p-4 text-foreground">
          {successMessage}
        </div>
      )}
      {errorMessage && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="flex justify-between items-center">
        <h3 className="font-semibold text-lg">Корреляционные правила</h3>
        <Button onClick={handleCreateNew} className="gap-2">
          <Plus className="h-4 w-4" />
          Создать правило
        </Button>
      </div>

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Загрузка правил...
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
          Правила не найдены
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-sm font-semibold">
                    <th className="px-4 py-3 text-left">Название</th>
                    <th className="px-4 py-3 text-left">Тип</th>
                    <th className="px-4 py-3 text-left">Активно</th>
                    <th className="px-4 py-3 text-left">Создано</th>
                    <th className="px-4 py-3 text-left">Действия</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((rule) => (
                    <tr
                      key={rule.id}
                      className="hover:bg-muted/40 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm font-medium">
                        {rule.name}
                        {rule.description && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {rule.description}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {RULE_TYPE_LABELS[rule.rule_type] || rule.rule_type}
                      </td>
                      <td className="px-4 py-3">
                        <Switch
                          checked={rule.enabled}
                          disabled={pendingToggleId === rule.id}
                          onCheckedChange={(enabled) =>
                            handleToggleEnabled(rule, enabled)
                          }
                        />
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(rule.created_at).toLocaleString("ru-RU")}
                      </td>
                      <td className="px-4 py-3 space-x-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEdit(rule)}
                          aria-label="Edit rule"
                        >
                          <Edit2 className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setDeleteTargetId(rule.id);
                            setDeleteConfirmOpen(true);
                          }}
                          aria-label="Delete rule"
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <SecurityPagination
            limit={limit}
            offset={offset}
            total={data.total}
            onLimitChange={setLimit}
            onOffsetChange={setOffset}
          />
        </>
      )}

      {/* Rule form modal */}
      <RuleForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={handleFormSubmit}
        initialRule={selectedRule || undefined}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Delete confirmation */}
      <Dialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Удалить правило?</DialogTitle>
            <DialogDescription>
              Это действие необратимо. Правило будет удалено из базы данных.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteConfirmOpen(false)}
            >
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Удаление..." : "Удалить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
