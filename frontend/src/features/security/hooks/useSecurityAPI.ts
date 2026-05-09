import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listEvents,
  listAlerts,
  getAlert,
  acknowledgeAlert,
  resolveAlert,
  listRules,
  getRule,
  createRule,
  updateRule,
  deleteRule,
  type CreateRuleInput,
} from "@/shared/api/security";

export type { CreateRuleInput };

// Events hooks
export function useEvents(
  limit: number = 50,
  offset: number = 0,
  filters?: {
    event_type?: string;
    severity?: string;
    from_timestamp?: string;
    to_timestamp?: string;
  },
) {
  return useQuery({
    queryKey: ["security", "events", { limit, offset, ...filters }],
    queryFn: () => listEvents(limit, offset, filters),
    staleTime: 10000,
  });
}

// Alerts hooks
export function useAlerts(
  limit: number = 50,
  offset: number = 0,
  filters?: {
    severity?: string;
    status?: string;
  },
) {
  return useQuery({
    queryKey: ["security", "alerts", { limit, offset, ...filters }],
    queryFn: () => listAlerts(limit, offset, filters),
    staleTime: 10000,
  });
}

export function useAlert(id: number) {
  return useQuery({
    queryKey: ["security", "alert", id],
    queryFn: () => getAlert(id),
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => acknowledgeAlert(id),
    onSuccess: (data) => {
      // Invalidate alerts list and specific alert
      queryClient.invalidateQueries({ queryKey: ["security", "alerts"] });
      queryClient.setQueryData(["security", "alert", data.id], data);
    },
  });
}

export function useResolveAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => resolveAlert(id),
    onSuccess: (data) => {
      // Invalidate alerts list and specific alert
      queryClient.invalidateQueries({ queryKey: ["security", "alerts"] });
      queryClient.setQueryData(["security", "alert", data.id], data);
    },
  });
}

// Rules hooks
export function useRules(limit: number = 50, offset: number = 0) {
  return useQuery({
    queryKey: ["security", "rules", { limit, offset }],
    queryFn: () => listRules(limit, offset),
    staleTime: 30000,
  });
}

export function useRule(id: number) {
  return useQuery({
    queryKey: ["security", "rule", id],
    queryFn: () => getRule(id),
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateRuleInput) => createRule(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security", "rules"] });
    },
  });
}

export function useUpdateRule(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CreateRuleInput>) => updateRule(id, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["security", "rules"] });
      queryClient.setQueryData(["security", "rule", id], data);
    },
  });
}

export function useUpdateAnyRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      input,
    }: {
      id: number;
      input: Partial<CreateRuleInput>;
    }) => updateRule(id, input),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["security", "rules"] });
      queryClient.setQueryData(["security", "rule", variables.id], data);
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security", "rules"] });
    },
  });
}
