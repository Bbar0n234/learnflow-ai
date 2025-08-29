import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth';

export const useAuthGuard = (requireAuth: boolean = true) => {
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!loading) {
      if (requireAuth && !isAuthenticated) {
        // Save current location for redirect after login
        const currentPath = location.pathname + location.search + location.hash;
        if (currentPath !== '/login') {
          sessionStorage.setItem('redirect_url', currentPath);
        }
        navigate('/login', { replace: true });
      } else if (!requireAuth && isAuthenticated) {
        // Redirect from login page if already authenticated
        const redirectUrl = sessionStorage.getItem('redirect_url') || '/';
        sessionStorage.removeItem('redirect_url');
        navigate(redirectUrl, { replace: true });
      }
    }
  }, [isAuthenticated, loading, requireAuth, navigate, location]);

  return { isAuthenticated, loading };
};