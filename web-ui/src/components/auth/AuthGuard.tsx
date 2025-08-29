import React, { useEffect } from 'react';
import type { ReactNode } from 'react';
import { useNavigate, useLocation, useParams } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

interface AuthGuardProps {
  children: ReactNode;
  requireAuth?: boolean;
  validateOwnership?: boolean;
}

export const AuthGuard: React.FC<AuthGuardProps> = ({ 
  children, 
  requireAuth = true,
  validateOwnership = false 
}) => {
  const { isAuthenticated, loading, currentUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams();

  useEffect(() => {
    if (!loading) {
      if (requireAuth && !isAuthenticated) {
        // Save current location for redirect after login
        const currentPath = location.pathname + location.search + location.hash;
        sessionStorage.setItem('redirect_url', currentPath);
        navigate('/login', { replace: true });
      } else if (validateOwnership && isAuthenticated && currentUser) {
        // Validate that the thread belongs to the current user
        const threadId = params.threadId;
        if (threadId && threadId !== currentUser.userId) {
          // Redirect to home if trying to access another user's thread
          navigate('/', { replace: true });
        }
      }
    }
  }, [isAuthenticated, loading, requireAuth, validateOwnership, currentUser, navigate, location, params]);

  // Show loading state
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-gray-900 dark:border-white"></div>
          <p className="mt-2 text-gray-600 dark:text-gray-400">Загрузка...</p>
        </div>
      </div>
    );
  }

  // Don't render children until auth check is complete
  if (requireAuth && !isAuthenticated) {
    return null;
  }

  return <>{children}</>;
};