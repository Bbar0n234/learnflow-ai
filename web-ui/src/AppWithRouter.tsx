import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Layout } from './components/Layout';
import { AccordionSidebar } from './components/AccordionSidebar';
import { MarkdownViewer } from './components/MarkdownViewer';
import { apiClient } from './services/ApiClient';
import { useApi } from './hooks/useApi';
import type { AppState, Thread, FileInfo } from './services/types';

function AppWithRouter() {
  const navigate = useNavigate();
  const params = useParams();
  const { threadId, sessionId } = params;
  const filePath = params['*']; // for wildcard route

  const [appState, setAppState] = useState<AppState>({
    selectedThread: null,
    selectedSession: null,
    selectedFile: null,
    currentFileContent: null,
    isLoading: false,
    error: null,
  });
  
  const [threads, setThreads] = useState<Thread[]>([]);
  const [sessionFiles, setSessionFiles] = useState<Map<string, FileInfo[]>>(new Map());
  const [threadsLoading, setThreadsLoading] = useState(true);
  const [initialLoad, setInitialLoad] = useState(true);

  const { executeRequest } = useApi();

  // Load threads on mount
  useEffect(() => {
    loadThreads();
  }, []);

  // Sync URL params with state on initial load and URL changes
  useEffect(() => {
    if (!initialLoad && threads.length > 0) {
      setAppState(prev => ({
        ...prev,
        selectedThread: threadId || null,
        selectedSession: sessionId || null,
        selectedFile: filePath || null,
      }));

      // Load data based on URL params
      if (threadId && sessionId && filePath) {
        loadFileContent(threadId, sessionId, filePath);
      } else if (threadId && sessionId) {
        loadSessionFiles(threadId, sessionId);
      }
    }
  }, [threadId, sessionId, filePath, threads, initialLoad]);

  // Mark initial load as complete when threads are loaded
  useEffect(() => {
    if (!threadsLoading && threads.length > 0 && initialLoad) {
      setInitialLoad(false);
    }
  }, [threadsLoading, threads, initialLoad]);

  const loadThreads = async () => {
    setThreadsLoading(true);
    try {
      const response = await executeRequest(apiClient.getThreads());
      if (response?.threads) {
        const threadsWithSessions = await Promise.all(
          response.threads.map(async (thread: Thread) => {
            const detail = await executeRequest(apiClient.getThread(thread.thread_id));
            return {
              ...thread,
              sessions: detail?.sessions || []
            };
          })
        );
        setThreads(threadsWithSessions);
      }
    } catch (error) {
      console.error('Failed to load threads:', error);
    } finally {
      setThreadsLoading(false);
    }
  };

  const loadSessionFiles = async (threadId: string, sessionId: string) => {
    const key = `${threadId}/${sessionId}`;
    if (!sessionFiles.has(key)) {
      try {
        const files = await executeRequest(apiClient.getSessionFiles(threadId, sessionId));
        if (files?.files) {
          setSessionFiles(prev => {
            const newMap = new Map(prev);
            newMap.set(key, files.files);
            return newMap;
          });
        }
      } catch (error) {
        console.error('Failed to load session files:', error);
      }
    }
  };

  const loadFileContent = async (threadId: string, sessionId: string, filePath: string) => {
    setAppState(prev => ({ ...prev, isLoading: true, error: null }));
    
    // First ensure session files are loaded
    await loadSessionFiles(threadId, sessionId);
    
    try {
      const content = await executeRequest(
        apiClient.getFileContent(threadId, sessionId, filePath)
      );
      setAppState(prev => ({
        ...prev,
        currentFileContent: content,
        isLoading: false,
      }));
    } catch (error) {
      setAppState(prev => ({
        ...prev,
        error: 'Failed to load file content',
        isLoading: false,
      }));
    }
  };

  const handleSelect = async (threadId: string, sessionId?: string, filePath?: string) => {
    // Build URL based on selection
    let url = '/';
    if (threadId) {
      url = `/thread/${threadId}`;
      if (sessionId) {
        url += `/session/${sessionId}`;
        if (filePath) {
          // Encode file path to handle special characters
          url += `/file/${encodeURIComponent(filePath).replace(/%2F/g, '/')}`;
        }
      }
    }
    
    // Navigate to new URL
    navigate(url);

    // Update state immediately for better UX
    setAppState(prev => ({
      ...prev,
      selectedThread: threadId,
      selectedSession: sessionId || null,
      selectedFile: filePath || null,
      currentFileContent: null,
    }));

    // Load data as needed
    if (sessionId && !sessionFiles.has(`${threadId}/${sessionId}`)) {
      await loadSessionFiles(threadId, sessionId);
    }

    if (filePath && sessionId) {
      await loadFileContent(threadId, sessionId, filePath);
    }
  };

  const renderMainContent = () => {
    if (appState.isLoading) {
      return (
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="text-center animate-fade-in">
            <div className="skeleton w-12 h-12 rounded-full mx-auto mb-4 animate-pulse"></div>
            <p className="text-muted">Loading content...</p>
          </div>
        </div>
      );
    }

    if (appState.selectedFile && appState.currentFileContent) {
      return (
        <div className="animate-fade-in">
          <MarkdownViewer content={appState.currentFileContent} />
        </div>
      );
    }

    return (
      <div className="flex flex-col min-h-[80vh]">
        <div className="py-12 border-b border-border/30 mb-12">
          <div className="flex items-center justify-center gap-6">
            <img 
              src="/logo_without_bg.png" 
              alt="LearnFlow AI" 
              className="h-24 w-auto object-contain animate-scale-in"
            />
          </div>
        </div>
        
        <div className="flex-1 flex items-start justify-center">
          <div className="text-center max-w-2xl px-6">
            <h2 className="text-[36px] font-bold leading-tight mb-4 animate-fade-in-up">
              Welcome to <span className="text-primary">LearnFlow AI</span>
            </h2>
            <p className="text-[17px] text-muted/80 mb-12 leading-relaxed max-w-lg mx-auto animate-fade-in-up animation-delay-100">
              Browse through threads, sessions, and files to explore your learning artifacts. 
              Start by selecting a thread from the sidebar.
            </p>
          </div>
        </div>
      </div>
    );
  };

  const sidebar = threadsLoading ? (
    <div className="flex items-center justify-center h-full">
      <div className="text-center">
        <div className="skeleton w-12 h-12 rounded-full mx-auto mb-4 animate-pulse"></div>
        <p className="text-muted text-sm">Loading threads...</p>
      </div>
    </div>
  ) : (
    <AccordionSidebar
      threads={threads}
      sessionFiles={sessionFiles}
      selectedThread={appState.selectedThread}
      selectedSession={appState.selectedSession}
      selectedFile={appState.selectedFile}
      onSelect={handleSelect}
    />
  );

  return (
    <Layout sidebar={sidebar}>
      {renderMainContent()}
    </Layout>
  );
}

export default AppWithRouter;