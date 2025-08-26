import axios from 'axios';
import type { AxiosInstance, AxiosError } from 'axios';
import type {
  ThreadsListResponse,
  ThreadDetailResponse,
  SessionFilesResponse,
  FileOperationResponse,
  ApiError
} from './types';

export class ApiClient {
  private baseURL: string;
  private axiosInstance: AxiosInstance;

  constructor(baseURL: string = import.meta.env.VITE_ARTIFACTS_API_URL || '/api') {
    this.baseURL = baseURL;
    this.axiosInstance = axios.create({
      baseURL: this.baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.setupInterceptors();
  }

  private setupInterceptors(): void {
    this.axiosInstance.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        const apiError: ApiError = {
          message: error.message || 'An unexpected error occurred',
          status: error.response?.status,
          details: error.response?.data as string,
        };
        return Promise.reject(apiError);
      }
    );
  }

  async getThreads(): Promise<ThreadsListResponse> {
    const response = await this.axiosInstance.get<ThreadsListResponse>('/threads');
    return response.data;
  }

  async getThread(threadId: string): Promise<ThreadDetailResponse> {
    const response = await this.axiosInstance.get<ThreadDetailResponse>(`/threads/${threadId}`);
    return response.data;
  }

  async getSessionFiles(threadId: string, sessionId: string): Promise<SessionFilesResponse> {
    const response = await this.axiosInstance.get<SessionFilesResponse>(
      `/threads/${threadId}/sessions/${sessionId}`
    );
    return response.data;
  }

  async getFileContent(threadId: string, sessionId: string, filePath: string): Promise<string> {
    const response = await this.axiosInstance.get<string>(
      `/threads/${threadId}/sessions/${sessionId}/${encodeURIComponent(filePath)}`,
      {
        headers: {
          'Accept': 'text/plain',
        },
      }
    );
    return response.data;
  }

  async createOrUpdateFile(
    threadId: string,
    sessionId: string,
    filePath: string,
    content: string
  ): Promise<FileOperationResponse> {
    const response = await this.axiosInstance.post<FileOperationResponse>(
      `/threads/${threadId}/sessions/${sessionId}/${encodeURIComponent(filePath)}`,
      { content },
      {
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );
    return response.data;
  }

  async deleteFile(
    threadId: string,
    sessionId: string,
    filePath: string
  ): Promise<FileOperationResponse> {
    const response = await this.axiosInstance.delete<FileOperationResponse>(
      `/threads/${threadId}/sessions/${sessionId}/${encodeURIComponent(filePath)}`
    );
    return response.data;
  }

  // Export methods
  async exportSingleDocument(
    threadId: string,
    sessionId: string,
    documentName: string,
    format: 'markdown' | 'pdf' = 'markdown'
  ): Promise<Blob> {
    const response = await this.axiosInstance.get(
      `/threads/${threadId}/sessions/${sessionId}/export/single`,
      {
        params: {
          document_name: documentName,
          format: format
        },
        responseType: 'blob'
      }
    );
    return response.data;
  }

  async exportPackage(
    threadId: string,
    sessionId: string,
    packageType: 'final' | 'all' = 'final',
    format: 'markdown' | 'pdf' = 'markdown'
  ): Promise<Blob> {
    const response = await this.axiosInstance.get(
      `/threads/${threadId}/sessions/${sessionId}/export/package`,
      {
        params: {
          package_type: packageType,
          format: format
        },
        responseType: 'blob'
      }
    );
    return response.data;
  }

  async getExportSettings(userId: string): Promise<any> {
    const response = await this.axiosInstance.get(
      `/users/${userId}/export-settings`
    );
    return response.data;
  }

  async updateExportSettings(userId: string, settings: any): Promise<any> {
    const response = await this.axiosInstance.put(
      `/users/${userId}/export-settings`,
      settings
    );
    return response.data;
  }

  async getRecentSessions(userId: string, limit: number = 5): Promise<any[]> {
    const response = await this.axiosInstance.get(
      `/users/${userId}/sessions/recent`,
      {
        params: { limit }
      }
    );
    return response.data;
  }

  // Helper method to trigger download
  downloadBlob(blob: Blob, filename: string): void {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }

  setBaseURL(url: string): void {
    this.baseURL = url;
    this.axiosInstance.defaults.baseURL = url;
  }
}

export const apiClient = new ApiClient();