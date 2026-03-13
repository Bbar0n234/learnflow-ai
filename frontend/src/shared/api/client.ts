import axios from "axios";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
  headers: {
    "X-User-Name": import.meta.env.VITE_USER_NAME ?? "default",
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("[API Error]", error.response?.status, error.response?.data);
    return Promise.reject(error);
  },
);
