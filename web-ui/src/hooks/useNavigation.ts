import { useNavigate, useParams } from 'react-router-dom';
import { useCallback } from 'react';

export const useNavigation = () => {
  const navigate = useNavigate();
  const params = useParams();
  
  const navigateToThread = useCallback((threadId: string) => {
    navigate(`/thread/${threadId}`);
  }, [navigate]);
  
  const navigateToSession = useCallback((threadId: string, sessionId: string) => {
    navigate(`/thread/${threadId}/session/${sessionId}`);
  }, [navigate]);
  
  const navigateToFile = useCallback((threadId: string, sessionId: string, filePath: string) => {
    // Encode file path but keep slashes for readability
    const encodedPath = encodeURIComponent(filePath).replace(/%2F/g, '/');
    navigate(`/thread/${threadId}/session/${sessionId}/file/${encodedPath}`);
  }, [navigate]);
  
  const navigateHome = useCallback(() => {
    navigate('/');
  }, [navigate]);
  
  const getCurrentRoute = useCallback(() => {
    const { threadId, sessionId } = params;
    const filePath = params['*'];
    
    return {
      threadId: threadId || null,
      sessionId: sessionId || null,
      filePath: filePath || null,
    };
  }, [params]);
  
  return {
    navigateToThread,
    navigateToSession,
    navigateToFile,
    navigateHome,
    getCurrentRoute,
  };
};