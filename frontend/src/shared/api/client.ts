import axios from "axios";

const USERNAME_KEY = "learnflow-username";

export function getUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? "";
}

export function setUsername(name: string): void {
  localStorage.setItem(USERNAME_KEY, name);
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
});

apiClient.interceptors.request.use((config) => {
  const username = getUsername();
  if (username) {
    config.headers["X-User-Name"] = username;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("[API Error]", error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
