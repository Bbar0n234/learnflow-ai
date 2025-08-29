import React, { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { apiClient } from '../services/ApiClient';
import { useApi } from '../hooks/useApi';

interface RouteGuardProps {
  threadId?: string;
  sessionId?: string;
  filePath?: string;
  fallbackPath?: string;
  children: React.ReactNode;
}

export const RouteGuard: React.FC<RouteGuardProps> = ({
  threadId,
  sessionId,
  filePath,
  fallbackPath = '/',
  children,
}) => {
  const [isValidating, setIsValidating] = useState(true);
  const [isValid, setIsValid] = useState(false);
  const { executeRequest } = useApi();

  useEffect(() => {
    const validateRoute = async () => {
      setIsValidating(true);
      
      try {
        // Validate thread exists
        if (threadId) {
          const threadResponse = await executeRequest(apiClient.getThread(threadId));
          if (!threadResponse) {
            setIsValid(false);
            setIsValidating(false);
            return;
          }
          
          // Validate session exists if provided
          if (sessionId) {
            const hasSession = threadResponse.sessions?.some(
              (s: any) => s.session_id === sessionId
            );
            
            if (!hasSession) {
              setIsValid(false);
              setIsValidating(false);
              return;
            }
            
            // Validate file exists if provided
            if (filePath) {
              const filesResponse = await executeRequest(
                apiClient.getSessionFiles(threadId, sessionId)
              );
              
              const hasFile = filesResponse?.files?.some(
                (f: any) => f.path === filePath
              );
              
              if (!hasFile) {
                setIsValid(false);
                setIsValidating(false);
                return;
              }
            }
          }
        }
        
        // All validations passed
        setIsValid(true);
      } catch (error) {
        console.error('Route validation failed:', error);
        setIsValid(false);
      } finally {
        setIsValidating(false);
      }
    };

    validateRoute();
  }, [threadId, sessionId, filePath, executeRequest]);

  if (isValidating) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center animate-fade-in">
          <div className="skeleton w-12 h-12 rounded-full mx-auto mb-4 animate-pulse"></div>
          <p className="text-muted">Validating route...</p>
        </div>
      </div>
    );
  }

  if (!isValid) {
    return <Navigate to={fallbackPath} replace />;
  }

  return <>{children}</>;
};