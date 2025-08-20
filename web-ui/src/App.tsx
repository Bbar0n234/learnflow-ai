import { useState, useEffect } from 'react';
import { Layout } from './components/Layout';
import { AccordionSidebar } from './components/AccordionSidebar';
import { MarkdownViewer } from './components/MarkdownViewer';
import { apiClient } from './services/ApiClient';
import { useApi } from './hooks/useApi';
import type { AppState, Thread, FileInfo } from './services/types';

function App() {
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

  const { executeRequest } = useApi();

  // Load threads on mount
  useEffect(() => {
    loadThreads();
  }, []);

  const loadThreads = async () => {
    setThreadsLoading(true);
    try {
      const response = await executeRequest(apiClient.getThreads());
      if (response?.threads) {
        // Load thread details with sessions for each thread
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

  const handleSelect = async (threadId: string, sessionId?: string, filePath?: string) => {
    // Update selection state
    setAppState(prev => ({
      ...prev,
      selectedThread: threadId,
      selectedSession: sessionId || null,
      selectedFile: filePath || null,
      currentFileContent: null,
    }));

    // Load session files if session is selected and not already loaded
    if (sessionId && !sessionFiles.has(`${threadId}/${sessionId}`)) {
      try {
        const files = await executeRequest(apiClient.getSessionFiles(threadId, sessionId));
        if (files?.files) {
          setSessionFiles(prev => {
            const newMap = new Map(prev);
            newMap.set(`${threadId}/${sessionId}`, files.files);
            return newMap;
          });
        }
      } catch (error) {
        console.error('Failed to load session files:', error);
      }
    }

    // Load file content if file is selected
    if (filePath && sessionId) {
      setAppState(prev => ({ ...prev, isLoading: true, error: null }));
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
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center max-w-md animate-fade-in">
          <div className="w-16 h-16 mx-auto mb-6 bg-primary/12 rounded-sm flex items-center justify-center">
            <svg className="w-8 h-8 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} 
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h2 className="display-h2 mb-3">
            Welcome to LearnFlow AI
          </h2>
          <p className="body-default text-muted mb-8 leading-relaxed">
            Browse through threads, sessions, and files to explore your learning artifacts. 
            Start by selecting a thread from the sidebar.
          </p>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div className="card-base p-4">
              <div className="caption-text text-info mb-1">1. Thread</div>
              <div className="body-text">Choose topic</div>
            </div>
            <div className="card-base p-4">
              <div className="caption-text text-primary mb-1">2. Session</div>
              <div className="body-text">Pick session</div>
            </div>
            <div className="card-base p-4">
              <div className="caption-text text-success mb-1">3. File</div>
              <div className="body-text">View content</div>
            </div>
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

export default App;
