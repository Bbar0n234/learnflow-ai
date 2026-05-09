import { apiClient } from "./client";

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export async function register(
  name: string,
  password: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/register", {
    name,
    password,
  });
  return data;
}

export async function login(
  name: string,
  password: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/login", {
    name,
    password,
  });
  return data;
}

export async function refresh(): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>("/auth/refresh");
  return data;
}

export interface UserInfo {
  id: string;
  name: string;
  is_admin?: boolean;
}

export function getIsAdminFromAccessToken(token: string | null): boolean {
  if (!token) return false;

  try {
    const parts = token.split(".");
    const payloadEncoded = parts.length === 3 ? parts[1] : undefined;
    if (!payloadEncoded) return false;

    const base64 = payloadEncoded.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "=",
    );
    const payload = JSON.parse(atob(padded));
    return payload.is_admin === true;
  } catch {
    return false;
  }
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await apiClient.get<UserInfo>("/auth/me");
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}
