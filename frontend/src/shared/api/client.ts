import axios from "axios";
import { logger } from "@/shared/lib/logger";

const ACCESS_TOKEN_KEY = "learnflow-access-token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
  withCredentials: true,
});

// Request interceptor: attach Bearer token
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: 401 → refresh → retry
let isRefreshing = false;
let pendingRequests: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processPendingRequests(token: string | null, error?: unknown) {
  for (const req of pendingRequests) {
    if (token) {
      req.resolve(token);
    } else {
      req.reject(error);
    }
  }
  pendingRequests = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url?.includes("/auth/")
    ) {
      originalRequest._retry = true;

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pendingRequests.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      isRefreshing = true;
      try {
        const { data } = await apiClient.post("/auth/refresh");
        const newToken = data.access_token;
        setAccessToken(newToken);
        processPendingRequests(newToken);
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processPendingRequests(null, refreshError);
        clearAccessToken();
        window.location.reload();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    logger.error("[API Error]", error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);

/**
 * Proactive token refresh for SSE/fetch requests that bypass axios.
 * Checks JWT expiry and refreshes if < 30s remaining.
 */
export async function ensureFreshToken(): Promise<string | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    const expiresIn = payload.exp - Date.now() / 1000;

    if (expiresIn > 30) return token;
  } catch {
    clearAccessToken();
    return null;
  }

  try {
    const { data } = await apiClient.post("/auth/refresh");
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    clearAccessToken();
    window.location.reload();
    return null;
  }
}
