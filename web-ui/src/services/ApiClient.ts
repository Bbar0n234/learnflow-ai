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

  setBaseURL(url: string): void {
    this.baseURL = url;
    this.axiosInstance.defaults.baseURL = url;
  }
}

export const apiClient = new ApiClient();