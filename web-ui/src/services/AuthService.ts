import axios, { AxiosError } from 'axios';

interface AuthResponse {
  access_token: string;
  token_type: string;
}

interface JWTPayload {
  sub: string;      // Telegram user ID
  username: string; // Telegram username
  exp: number;      // Expiration timestamp
  iat: number;      // Issued at timestamp
}

interface UserInfo {
  userId: string;
  username: string;
}

interface RetryConfig {
  maxRetries: number;
  initialDelay: number;
  maxDelay: number;
  backoffFactor: number;
}

const TOKEN_KEY = 'auth_token';
const TOKEN_EXPIRY_KEY = 'token_expiry';

const DEFAULT_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  initialDelay: 1000, // 1 second
  maxDelay: 10000,    // 10 seconds
  backoffFactor: 2
};

export class AuthService {
  private baseURL: string;
  private retryConfig: RetryConfig;

  constructor(
    baseURL: string = import.meta.env.VITE_ARTIFACTS_API_URL || '/api',
    retryConfig: Partial<RetryConfig> = {}
  ) {
    this.baseURL = baseURL;
    this.retryConfig = { ...DEFAULT_RETRY_CONFIG, ...retryConfig };
  }

  private async sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  private shouldRetry(error: AxiosError): boolean {
    // Don't retry on client errors (4xx) except for 408 (Request Timeout) and 429 (Too Many Requests)
    if (error.response) {
      const status = error.response.status;
      if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
        return false;
      }
    }
    
    // Retry on network errors or 5xx server errors
    return !error.response || error.response.status >= 500;
  }

  private async retryRequest<T>(
    requestFn: () => Promise<T>,
    retryCount: number = 0
  ): Promise<T> {
    try {
      return await requestFn();
    } catch (error) {
      if (!axios.isAxiosError(error)) {
        throw error;
      }

      const isRetryable = this.shouldRetry(error);
      const hasRetriesLeft = retryCount < this.retryConfig.maxRetries;

      if (!isRetryable || !hasRetriesLeft) {
        throw error;
      }

      // Calculate delay with exponential backoff
      const delay = Math.min(
        this.retryConfig.initialDelay * Math.pow(this.retryConfig.backoffFactor, retryCount),
        this.retryConfig.maxDelay
      );

      await this.sleep(delay);

      return this.retryRequest(requestFn, retryCount + 1);
    }
  }

  async login(username: string, code: string): Promise<UserInfo> {
    try {
      const response = await this.retryRequest(async () => {
        return axios.post<AuthResponse>(
          `${this.baseURL}/auth/verify`,
          {
            username,
            code
          },
          {
            timeout: 10000 // 10 second timeout per request
          }
        );
      });

      const token = response.data.access_token;
      this.saveToken(token);
      
      return this.getCurrentUser()!;
    } catch (error) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 401) {
          throw new Error('Неверный код или код истёк. Попробуйте получить новый код через /web_auth в Telegram.');
        } else if (error.response?.status === 400) {
          throw new Error('Неверный формат данных. Проверьте введённые данные.');
        } else if (error.code === 'ECONNABORTED') {
          throw new Error('Превышено время ожидания ответа от сервера. Проверьте соединение и попробуйте снова.');
        }
      }
      throw new Error('Ошибка соединения с сервером. Попробуйте позже.');
    }
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_EXPIRY_KEY);
    sessionStorage.removeItem('redirect_url');
  }

  getToken(): string | null {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) return null;

    const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
    if (expiry) {
      const expiryTime = parseInt(expiry, 10);
      if (Date.now() > expiryTime) {
        this.logout();
        return null;
      }
    }

    return token;
  }

  getCurrentUser(): UserInfo | null {
    const token = this.getToken();
    if (!token) return null;

    try {
      const payload = this.parseJWT(token);
      return {
        userId: payload.sub,  // Telegram user ID (e.g., "123456789")
        username: payload.username || payload.sub  // Telegram username or fallback to user_id
      };
    } catch {
      return null;
    }
  }

  isAuthenticated(): boolean {
    return this.getToken() !== null;
  }

  private saveToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    
    try {
      const payload = this.parseJWT(token);
      const expiryTime = payload.exp * 1000;
      localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
    } catch {
      // If JWT parsing fails, set expiry to 24 hours from now
      const expiryTime = Date.now() + 24 * 60 * 60 * 1000;
      localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
    }
  }

  private parseJWT(token: string): JWTPayload {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid JWT format');
    }

    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    return JSON.parse(decoded);
  }

  setBaseURL(url: string): void {
    this.baseURL = url;
  }
}

export const authService = new AuthService();