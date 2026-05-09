// Security Event types for SIEM API

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
