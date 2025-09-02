import axios from 'axios';
import type { AxiosInstance, AxiosError } from 'axios';
import type {
  ThreadsListResponse,
  ThreadDetailResponse,
  SessionFilesResponse,
  FileOperationResponse,
  ApiError
} from './types';
import { authService } from './AuthService';

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
    // Request interceptor to add auth token
    this.axiosInstance.interceptors.request.use(
      (config) => {
        const token = authService.getToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor for error handling
    this.axiosInstance.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        // Handle 401 Unauthorized - token expired or invalid
        if (error.response?.status === 401) {
          authService.logout();
          window.location.href = '/login';
        }
        
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
    const user = authService.getCurrentUser();
    if (!user) {
      throw new Error('User not authenticated');
    }
    
    // Filter threads by current user ID
    const response = await this.axiosInstance.get<ThreadsListResponse>('/threads', {
      params: {
        user_id: user.userId
      }
    });
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
      `/threads/${threadId}/sessions/${sessionId}/files/${encodeURIComponent(filePath)}`,
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
      `/threads/${threadId}/sessions/${sessionId}/files/${encodeURIComponent(filePath)}`,
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
      `/threads/${threadId}/sessions/${sessionId}/files/${encodeURIComponent(filePath)}`
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
        responseType: 'blob',
        // Increase timeout for export operations (3 minutes)
        timeout: 180000
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
        responseType: 'blob',
        // Increase timeout for package exports (5 minutes)
        // Package exports can take longer, especially with PDF conversion
        timeout: 300000
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