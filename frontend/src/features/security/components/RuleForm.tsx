import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { Switch } from "@/shared/ui/switch";
import { Textarea } from "@/shared/ui/textarea";
import {
  CorrelationRule,
  RuleType,
  RuleConfig,
  Severity,
} from "@/types/security";
import { CreateRuleInput } from "@/shared/api/security";

const RULE_TYPES: Array<{ value: RuleType; label: string }> = [
  { value: "threshold", label: "Порог" },
  { value: "sequence", label: "Последовательность" },
  { value: "aggregate", label: "Агрегат" },
];

const GROUP_KEY_OPTIONS = [
  { value: null, label: "Без группировки" },
  { value: "ip", label: "По IP" },
  { value: "user_id", label: "По пользователю" },
  { value: "thread_id", label: "По потоку" },
];

const SEVERITY_OPTIONS = [
  { value: "info", label: "Информация" },
  { value: "warning", label: "Предупреждение" },
  { value: "critical", label: "Критично" },
];

interface RuleFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (input: CreateRuleInput) => Promise<void>;
  initialRule?: CorrelationRule;
  isLoading?: boolean;
}

export function RuleForm({
  open,
  onOpenChange,
  onSubmit,
  initialRule,
  isLoading = false,
}: RuleFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [ruleType, setRuleType] = useState<RuleType>("threshold");
  const [enabled, setEnabled] = useState(true);

  // Common config
  const [window, setWindow] = useState<number | string>(60);
  const [threshold, setThreshold] = useState<number | string>(5);
  const [groupKey, setGroupKey] = useState<string | null | "">("ip");
  const [eventTypePattern, setEventTypePattern] = useState("");

  // Sequence config
  const [sequenceA, setSequenceA] = useState("");
  const [sequenceB, setSequenceB] = useState("");

  // Severity
  const [severity, setSeverity] = useState<Severity>("critical");

  // Submission error
  const [submitError, setSubmitError] = useState("");

  useEffect(() => {
    if (initialRule) {
      setName(initialRule.name);
      setDescription(initialRule.description || "");
      setRuleType(initialRule.rule_type);
      setEnabled(initialRule.enabled);

      const config = initialRule.config as Record<string, unknown>;
      if (typeof config.window === "number") setWindow(config.window);
      if (typeof config.threshold === "number") setThreshold(config.threshold);
      if (config.group_key !== undefined)
        setGroupKey((config.group_key as string | null) || null);
      if (typeof config.event_type_pattern === "string")
        setEventTypePattern(config.event_type_pattern);
      if (typeof config.sequence_a === "string")
        setSequenceA(config.sequence_a);
      if (typeof config.sequence_b === "string")
        setSequenceB(config.sequence_b);
      if (typeof config.severity === "string")
        setSeverity(config.severity as Severity);
    }
  }, [initialRule, open]);

  const handleSubmit = async () => {
    setSubmitError("");

    // Validate required fields
    if (!name.trim()) {
      setSubmitError("Название правила обязательно");
      return;
    }

    if (!window || window === "") {
      setSubmitError("Временное окно обязательно");
      return;
    }

    const config: RuleConfig = {
      window: typeof window === "number" ? window : parseInt(String(window)),
      severity,
    };

    if (ruleType === "threshold" || ruleType === "aggregate") {
      if (!eventTypePattern.trim()) {
        setSubmitError("Шаблон типа события обязателен");
        return;
      }
      if (!threshold || threshold === "") {
        setSubmitError("Порог обязателен");
        return;
      }
      config.event_type_pattern = eventTypePattern;
      config.threshold =
        typeof threshold === "number" ? threshold : parseInt(String(threshold));

      if (ruleType === "threshold") {
        config.group_key = groupKey === "" ? null : groupKey;
      }
    } else if (ruleType === "sequence") {
      if (!sequenceA.trim() || !sequenceB.trim()) {
        setSubmitError("Оба события в последовательности обязательны");
        return;
      }
      config.sequence_a = sequenceA;
      config.sequence_b = sequenceB;
      config.group_key = groupKey === "" ? null : groupKey;
    }

    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || undefined,
        rule_type: ruleType,
        enabled,
        config,
      });
      onOpenChange(false);
    } catch (err) {
      setSubmitError(
        err instanceof Error ? err.message : "Ошибка при сохранении правила",
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {initialRule ? "Редактировать правило" : "Создать новое правило"}
          </DialogTitle>
          <DialogDescription>
            Настройте параметры корреляции для обнаружения инцидентов
          </DialogDescription>
        </DialogHeader>

        {submitError && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-800 text-sm">
            {submitError}
          </div>
        )}

        <div className="space-y-4">
          {/* Basic fields */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Название
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="brute_force_auth"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Тип правила
              </label>
              <Select
                value={ruleType}
                onValueChange={(v) => setRuleType(v as RuleType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {RULE_TYPES.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Описание
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание правила и его назначение"
              rows={2}
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-foreground">
              Активно
            </label>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>

          {/* Common config */}
          <div className="border-t border-border pt-4 space-y-4">
            <h4 className="font-medium text-sm">Конфигурация</h4>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Временное окно (сек)
                </label>
                <Input
                  type="number"
                  value={window === "" ? "" : String(window)}
                  onChange={(e) =>
                    setWindow(
                      e.target.value === "" ? "" : parseInt(e.target.value),
                    )
                  }
                  min={1}
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Серьезность алерта
                </label>
                <Select
                  value={severity}
                  onValueChange={(v) => setSeverity(v as Severity)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SEVERITY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Threshold or Aggregate */}
            {(ruleType === "threshold" || ruleType === "aggregate") && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Шаблон типа события
                  </label>
                  <Input
                    value={eventTypePattern}
                    onChange={(e) => setEventTypePattern(e.target.value)}
                    placeholder="auth.login.failed или agent.guard.%.injection"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Порог срабатывания
                  </label>
                  <Input
                    type="number"
                    value={threshold === "" ? "" : String(threshold)}
                    onChange={(e) =>
                      setThreshold(
                        e.target.value === "" ? "" : parseInt(e.target.value),
                      )
                    }
                    min={1}
                  />
                </div>
              </div>
            )}

            {/* Threshold specific */}
            {ruleType === "threshold" && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Группировать по
                </label>
                <Select
                  value={String(groupKey ?? "")}
                  onValueChange={(v) => setGroupKey(v === "" ? null : v)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {GROUP_KEY_OPTIONS.map((opt) => (
                      <SelectItem
                        key={String(opt.value)}
                        value={String(opt.value ?? "")}
                      >
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {/* Sequence specific */}
            {ruleType === "sequence" && (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Событие А (шаблон)
                  </label>
                  <Input
                    value={sequenceA}
                    onChange={(e) => setSequenceA(e.target.value)}
                    placeholder="auth.login.failed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Событие Б (шаблон)
                  </label>
                  <Input
                    value={sequenceB}
                    onChange={(e) => setSequenceB(e.target.value)}
                    placeholder="agent.guard.input.injection"
                  />
                </div>

                <div className="col-span-2">
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Группировать по (опционально)
                  </label>
                  <Select
                    value={String(groupKey ?? "")}
                    onValueChange={(v) => setGroupKey(v === "" ? null : v)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {GROUP_KEY_OPTIONS.map((opt) => (
                        <SelectItem
                          key={String(opt.value)}
                          value={String(opt.value ?? "")}
                        >
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={handleSubmit} disabled={isLoading}>
            {isLoading ? "Сохранение..." : "Сохранить"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
