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

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30000,
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

// Endpoints that issue or refresh credentials and are called without a valid
// access token — a 401 from these is not "my session expired", so it must not
// enter the refresh-retry flow. Everything else (including /auth/me and
// /auth/logout) is called on behalf of an already-authenticated user and goes
// through the standard single-flight refresh + retry below.
//
// /auth/refresh stays in this list on purpose: it's the request that repairs
// a stale access token, so retrying it through itself would recurse.
//
// Extension point for OAuth routes: classify by the same rule — start/callback
// endpoints reached before a token is issued go here, endpoints reached with a
// token do not. Write each entry as the request path exactly as it is passed to
// apiClient, relative to its baseURL ("/auth/oauth/yandex/callback"): matching
// is on the whole path, not on a substring, so a fragment of a path ("/oauth")
// or a path carrying a query string will not match anything.
const CREDENTIAL_ENDPOINTS = ["/auth/refresh", "/auth/login", "/auth/register"];

// axios resolves a request URL against baseURL unless the URL is already
// absolute, so classification resolves it the same way before comparing:
// "/auth/login", "/api/auth/login" and "http://host/api/auth/login?next=/" name
// one endpoint and must normalize alike. Query, hash and a trailing slash drop
// out; what is left is a bare path.
const ABSOLUTE_URL = /^([a-z][a-z\d+\-.]*:)?\/\//i;

function normalizeRequestPath(url: string): string {
  const resolved = ABSOLUTE_URL.test(url)
    ? url
    : `${API_BASE_URL.replace(/\/+$/, "")}/${url.replace(/^\/+/, "")}`;
  // The fallback origin is only consumed when the API base is itself relative
  // ("/api"); an absolute `resolved` ignores it. Either way the path matches.
  return new URL(resolved, "http://localhost").pathname.replace(/\/+$/, "");
}

const CREDENTIAL_PATHS = CREDENTIAL_ENDPOINTS.map(normalizeRequestPath);

function requiresAccessToken(url: string | undefined): boolean {
  if (!url) return true;
  return !CREDENTIAL_PATHS.includes(normalizeRequestPath(url));
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      requiresAccessToken(originalRequest.url)
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
    const parts = token.split(".");
    if (parts.length !== 3) {
      clearAccessToken();
      return null;
    }
    const payload = JSON.parse(atob(parts[1]!));
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
