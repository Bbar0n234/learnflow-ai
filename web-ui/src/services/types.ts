export interface Thread {
  thread_id: string;
  sessions_count: number;
  created: string;
  last_activity: string;
  sessions?: Session[];
}

export interface Session {
  session_id: string;
  files_count: number;
  created: string;
  modified: string;
  input_content?: string;
  display_name?: string | null;
  status?: string;
}

export interface FileInfo {
  path: string;
  size: number;
  modified: string;
  content_type: string;
}

export interface ThreadsListResponse {
  threads: Thread[];
}

export interface ThreadDetailResponse {
  thread_id: string;
  sessions: Session[];
  created: string;
  last_activity: string;
  sessions_count: number;
}

export interface SessionFilesResponse {
  files: FileInfo[];
  total: number;
}

export interface FileOperationResponse {
  success: boolean;
  message: string;
  file?: FileInfo;
}

export interface AppState {
  selectedThread: string | null;
  selectedSession: string | null;
  selectedFile: string | null;
  currentFileContent: string | null;
  isLoading: boolean;
  error: string | null;
}

export interface ApiError {
  message: string;
  status?: number;
  details?: string;
}