import React, { createContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import { authService } from '../services/AuthService';

interface UserInfo {
  userId: string;
  username: string;
}

interface AuthContextType {
  isAuthenticated: boolean;
  currentUser: UserInfo | null;
  loading: boolean;
  login: (username: string, code: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => void;
}

export const AuthContext = createContext<AuthContextType>({
  isAuthenticated: false,
  currentUser: null,
  loading: true,
  login: async () => {},
  logout: () => {},
  checkAuth: () => {},
});

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(() => {
    setLoading(true);
    try {
      const user = authService.getCurrentUser();
      if (user) {
        setIsAuthenticated(true);
        setCurrentUser(user);
      } else {
        setIsAuthenticated(false);
        setCurrentUser(null);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setIsAuthenticated(false);
      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = async (username: string, code: string): Promise<void> => {
    setLoading(true);
    try {
      const user = await authService.login(username, code);
      setIsAuthenticated(true);
      setCurrentUser(user);
      
      // Restore redirect URL if it exists
      const redirectUrl = sessionStorage.getItem('redirect_url');
      if (redirectUrl) {
        sessionStorage.removeItem('redirect_url');
        window.location.href = redirectUrl;
      }
    } finally {
      setLoading(false);
    }
  };

  const logout = useCallback(() => {
    authService.logout();
    setIsAuthenticated(false);
    setCurrentUser(null);
    // Redirect to login page
    window.location.href = '/login';
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        currentUser,
        loading,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};