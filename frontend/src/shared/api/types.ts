// === Entities (GET list/detail, PUT responses) ===

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface Chat {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  security_blocked: boolean;
}

export interface ChatDetail {
  thread_id: string;
  title: string;
  security_blocked: boolean;
  messages: Message[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  artifacts: Artifact[];
  trace_id?: string | null;
  feedback_score?: boolean | null;
  redacted?: boolean;
}

export interface RecentChat {
  thread_id: string;
  title: string;
  project_id: string;
  project_name: string;
  updated_at: string;
  security_blocked: boolean;
}

export interface Sphere {
  project_id: string;
  content: string;
  updated_at: string;
}

export interface Artifact {
  id: string;
  title: string;
  type: string;
  created_at: string;
}

export interface ArtifactDetail {
  id: string;
  title: string;
  type: string;
  content: string;
  thread_id: string | null;
  message_id: string | null;
  created_at: string;
}

// === Requests ===

export interface CreateProjectRequest {
  name: string;
}

export interface UpdateProjectRequest {
  name: string;
}

export interface CreateChatRequest {
  title?: string;
}

export interface UpdateSphereRequest {
  content: string;
}

export interface SendMessageRequest {
  content: string;
}

// === Responses (list wrappers) ===

// Канонический envelope списочных ответов: items + pagination metadata
export interface ListResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

// === Settings (Track A) ===

export interface AvailableModel {
  name: string;
  display_name: string;
}

export interface Settings {
  model_name: string | null;
  extra_body: object | null;
  resolved_model: string;
  resolved_source: string;
}

export interface SettingsUpdate {
  model_name: string | null;
  extra_body?: object | null;
}

// === User Memory (Track B) ===

export interface Instructions {
  content: string;
}

export interface MemoryItem {
  key: string;
  description: string;
  content: string;
  created_at: string;
}

// === MCP Servers (Track C) ===

export interface MCPServer {
  id: string;
  name: string;
  transport: string;
  url: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  allowed_tools: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InheritedMCPServer {
  id: string;
  name: string;
  transport: string;
  url: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  is_active: boolean;
  is_disabled: boolean;
}

export interface MCPServerListResponse extends ListResponse<MCPServer> {
  inherited: InheritedMCPServer[];
}

export interface MCPServerCreate {
  name: string;
  transport: "http" | "sse";
  url: string;
  api_key?: string;
}

export interface MCPServerUpdate {
  name?: string;
  transport?: "http" | "sse";
  url?: string;
  api_key?: string;
  is_active?: boolean;
}

export interface TestConnectionResult {
  success: boolean;
  tools: string[];
  error?: string;
}

// === SSE Events ===

export type SSEEvent =
  | { type: "text_chunk"; content: string }
  | { type: "tool_start"; tool: string; call_id: string }
  | { type: "tool_end"; tool: string; call_id: string }
  | {
      type: "artifact_created";
      id: string;
      title: string;
      artifact_type: string;
    }
  | { type: "done"; message_id?: string; trace_id?: string }
  | { type: "error"; detail: string }
  | { type: "security_block"; reason: string }
  | { type: "final_output_review_started" }
  | { type: "final_output_review_complete" };
