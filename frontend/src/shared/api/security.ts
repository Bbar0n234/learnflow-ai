import axios from "axios";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./query-keys";

// === Types (SIEM API) ===

export type Severity = "info" | "warning" | "critical";
export type AlertStatus = "new" | "acknowledged" | "resolved";
export type RuleType = "threshold" | "sequence" | "aggregate";

export interface SecurityEventIdentifiers {
  ip?: string;
  user_id?: string;
  request_id?: string;
  thread_id?: string;
  project_id?: string;
  session_id?: string;
  user_agent_hash?: string;
}

export interface SecurityEvent {
  id: number;
  event_id: string; // UUID
  event_type: string;
  severity: Severity;
  event_timestamp: string; // ISO8601
  ingested_at: string; // ISO8601
  identifiers: SecurityEventIdentifiers;
  metadata: Record<string, unknown>;
  created_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SecurityAlert {
  id: number;
  rule_id: number;
  severity: Severity;
  status: AlertStatus;
  group_key?: string;
  matched_events_count: number;
  first_event_id?: number;
  latest_event_id?: number;
  created_at: string;
  acknowledged_at?: string;
  resolved_at?: string;
  acknowledged_by?: string;
  resolved_by?: string;
  updated_at: string;
}

export interface CorrelationRule {
  id: number;
  name: string;
  description?: string;
  rule_type: RuleType;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface RuleConfig {
  window?: number; // seconds
  group_key?: string | null; // ip, user_id, thread_id, or null
  threshold?: number;
  event_type_pattern?: string;
  sequence_a?: string;
  sequence_b?: string;
  severity?: Severity;
  [key: string]: unknown;
}

export interface CreateRuleInput {
  name: string;
  description?: string;
  rule_type: RuleType;
  enabled: boolean;
  config: RuleConfig;
}

// === Client ===

const VITE_SIEM_API_URL = import.meta.env.VITE_SIEM_API_URL ?? "/siem/api";

// Отдельный axios instance под SIEM API; токен берёт из того же хранилища, что main app.
export const siemClient = axios.create({
  baseURL: VITE_SIEM_API_URL,
  withCredentials: true,
});

siemClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("learnflow-access-token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// === API ===

export async function listEvents(
  limit: number = 50,
  offset: number = 0,
  filters?: {
    event_type?: string;
    severity?: string;
    from_timestamp?: string;
    to_timestamp?: string;
  },
): Promise<PaginatedResponse<SecurityEvent>> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  params.append("offset", offset.toString());
  if (filters?.event_type) params.append("event_type", filters.event_type);
  if (filters?.severity) params.append("severity", filters.severity);
  if (filters?.from_timestamp) params.append("from", filters.from_timestamp);
  if (filters?.to_timestamp) params.append("to", filters.to_timestamp);

  const { data } = await siemClient.get<PaginatedResponse<SecurityEvent>>(
    `/security/events?${params.toString()}`,
  );
  return data;
}

export async function listAlerts(
  limit: number = 50,
  offset: number = 0,
  filters?: {
    severity?: string;
    status?: string;
  },
): Promise<PaginatedResponse<SecurityAlert>> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  params.append("offset", offset.toString());
  if (filters?.severity) params.append("severity", filters.severity);
  if (filters?.status) params.append("status", filters.status);

  const { data } = await siemClient.get<PaginatedResponse<SecurityAlert>>(
    `/security/alerts?${params.toString()}`,
  );
  return data;
}

export async function getAlert(id: number): Promise<SecurityAlert> {
  const { data } = await siemClient.get<SecurityAlert>(
    `/security/alerts/${id}`,
  );
  return data;
}

export async function acknowledgeAlert(id: number): Promise<SecurityAlert> {
  const { data } = await siemClient.patch<SecurityAlert>(
    `/security/alerts/${id}`,
    { status: "acknowledged" },
  );
  return data;
}

export async function resolveAlert(id: number): Promise<SecurityAlert> {
  const { data } = await siemClient.patch<SecurityAlert>(
    `/security/alerts/${id}`,
    { status: "resolved" },
  );
  return data;
}

export async function listRules(
  limit: number = 50,
  offset: number = 0,
): Promise<PaginatedResponse<CorrelationRule>> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  params.append("offset", offset.toString());

  const { data } = await siemClient.get<PaginatedResponse<CorrelationRule>>(
    `/security/rules?${params.toString()}`,
  );
  return data;
}

export async function getRule(id: number): Promise<CorrelationRule> {
  const { data } = await siemClient.get<CorrelationRule>(
    `/security/rules/${id}`,
  );
  return data;
}

export async function createRule(
  input: CreateRuleInput,
): Promise<CorrelationRule> {
  const { data } = await siemClient.post<CorrelationRule>(
    `/security/rules`,
    input,
  );
  return data;
}

export async function updateRule(
  id: number,
  input: Partial<CreateRuleInput>,
): Promise<CorrelationRule> {
  const { data } = await siemClient.patch<CorrelationRule>(
    `/security/rules/${id}`,
    input,
  );
  return data;
}

export async function deleteRule(id: number): Promise<void> {
  await siemClient.delete(`/security/rules/${id}`);
}

// === Hooks ===

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
    queryKey: queryKeys.security.events({ limit, offset, ...filters }),
    queryFn: () => listEvents(limit, offset, filters),
    staleTime: 10000,
  });
}

export function useAlerts(
  limit: number = 50,
  offset: number = 0,
  filters?: {
    severity?: string;
    status?: string;
  },
) {
  return useQuery({
    queryKey: queryKeys.security.alertsList({ limit, offset, ...filters }),
    queryFn: () => listAlerts(limit, offset, filters),
    staleTime: 10000,
  });
}

export function useAlert(id: number) {
  return useQuery({
    queryKey: queryKeys.security.alert(id),
    queryFn: () => getAlert(id),
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => acknowledgeAlert(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.alerts });
      queryClient.setQueryData(queryKeys.security.alert(data.id), data);
    },
  });
}

export function useResolveAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => resolveAlert(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.alerts });
      queryClient.setQueryData(queryKeys.security.alert(data.id), data);
    },
  });
}

export function useRules(limit: number = 50, offset: number = 0) {
  return useQuery({
    queryKey: queryKeys.security.rulesList({ limit, offset }),
    queryFn: () => listRules(limit, offset),
    staleTime: 30000,
  });
}

export function useRule(id: number) {
  return useQuery({
    queryKey: queryKeys.security.rule(id),
    queryFn: () => getRule(id),
  });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateRuleInput) => createRule(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules });
    },
  });
}

export function useUpdateRule(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CreateRuleInput>) => updateRule(id, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules });
      queryClient.setQueryData(queryKeys.security.rule(id), data);
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
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules });
      queryClient.setQueryData(queryKeys.security.rule(variables.id), data);
    },
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.security.rules });
    },
  });
}
