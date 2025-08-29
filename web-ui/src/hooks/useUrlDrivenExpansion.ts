import { useParams } from 'react-router-dom';
import { useMemo } from 'react';

export const useUrlDrivenExpansion = () => {
  const params = useParams();
  const { threadId, sessionId } = params;
  const filePath = params['*']; // for wildcard route
  
  const expanded = useMemo(() => {
    const expandedThreads = new Set<string>();
    const expandedSessions = new Set<string>();
    const expandedFolders = new Set<string>();
    
    // If there's a threadId in URL - expand this thread
    if (threadId) {
      expandedThreads.add(threadId);
    }
    
    // If there's a sessionId in URL - expand this session
    if (sessionId && threadId) {
      expandedSessions.add(`${threadId}-${sessionId}`);
    }
    
    // If there's a file with path - expand folders
    if (filePath && filePath.includes('/')) {
      const parts = filePath.split('/');
      parts.pop(); // remove file name
      
      let currentPath = '';
      parts.forEach(folder => {
        currentPath = currentPath ? `${currentPath}/${folder}` : folder;
        expandedFolders.add(`${threadId}-${sessionId}-${currentPath}`);
      });
    }
    
    return {
      threads: expandedThreads,
      sessions: expandedSessions,
      folders: expandedFolders
    };
  }, [threadId, sessionId, filePath]);
  
  return expanded;
};