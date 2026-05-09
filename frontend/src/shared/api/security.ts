import axios from "axios";
import {
  SecurityEvent,
  SecurityAlert,
  CorrelationRule,
  PaginatedResponse,
  RuleType,
  RuleConfig,
} from "@/types/security";

const VITE_SIEM_API_URL =
  import.meta.env.VITE_SIEM_API_URL ?? "http://localhost:8001/api";

// Create a separate axios instance for SIEM API
// It will share the same token interceptor as the main app
export const siemClient = axios.create({
  baseURL: VITE_SIEM_API_URL,
  withCredentials: true,
});

// Share token with main API client
siemClient.interceptors.request.use((config) => {
  // Get token from same storage as main app
  const token = localStorage.getItem("learnflow-access-token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Export API functions
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

export interface CreateRuleInput {
  name: string;
  description?: string;
  rule_type: RuleType;
  enabled: boolean;
  config: RuleConfig;
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
