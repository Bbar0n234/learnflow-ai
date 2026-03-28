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
}

export interface ChatDetail {
  thread_id: string;
  title: string;
  messages: Message[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  artifacts: Artifact[];
}

export interface RecentChat {
  thread_id: string;
  title: string;
  project_id: string;
  project_name: string;
  updated_at: string;
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

export interface ListResponse<T> {
  items: T[];
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
  | { type: "error"; detail: string };
