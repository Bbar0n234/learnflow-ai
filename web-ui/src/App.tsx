import { useState } from 'react';
import { Layout } from './components/Layout';
import { ThreadsList } from './components/ThreadsList';
import { SessionsList } from './components/SessionsList';
import { FileExplorer } from './components/FileExplorer';
import { MarkdownViewer } from './components/MarkdownViewer';
import { apiClient } from './services/ApiClient';
import { useApi } from './hooks/useApi';
import type { AppState } from './services/types';

function App() {
  const [appState, setAppState] = useState<AppState>({
    selectedThread: null,
    selectedSession: null,
    selectedFile: null,
    currentFileContent: null,
    isLoading: false,
    error: null,
  });

  const { executeRequest } = useApi();

  const handleThreadSelect = (threadId: string) => {
    setAppState(prev => ({
      ...prev,
      selectedThread: threadId,
      selectedSession: null,
      selectedFile: null,
      currentFileContent: null,
    }));
  };

  const handleSessionSelect = (sessionId: string) => {
    setAppState(prev => ({
      ...prev,
      selectedSession: sessionId,
      selectedFile: null,
      currentFileContent: null,
    }));
  };

  const handleFileSelect = async (filePath: string) => {
    if (!appState.selectedThread || !appState.selectedSession) return;

    setAppState(prev => ({
      ...prev,
      selectedFile: filePath,
      isLoading: true,
      error: null,
    }));

    const content = await executeRequest(
      apiClient.getFileContent(appState.selectedThread, appState.selectedSession, filePath)
    );

    setAppState(prev => ({
      ...prev,
      currentFileContent: content,
      isLoading: false,
    }));
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
          {/* Document Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              <div className="status-dot-success"></div>
              <h1 className="display-h2">
                {appState.selectedFile?.split('/').pop() || appState.selectedFile}
              </h1>
            </div>
            <div className="flex items-center gap-3">
              <span className="chip-info">
                Thread: {appState.selectedThread?.slice(0, 8)}...
              </span>
              <span className="chip-primary">
                Session: {appState.selectedSession?.slice(0, 12)}...
              </span>
            </div>
          </div>
          
          {/* Content */}
          <div className="section-divider">
            <MarkdownViewer content={appState.currentFileContent} />
          </div>
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

  const sidebar = (
    <div className="h-full flex flex-col">
      <div className="sidebar-section">
        <div className="sidebar-section-header">
          Navigation
        </div>
        <div className="space-y-6">
          <ThreadsList
            selectedThread={appState.selectedThread}
            onThreadSelect={handleThreadSelect}
          />
          {appState.selectedThread && (
            <div className="animate-fade-in">
              <SessionsList
                threadId={appState.selectedThread}
                selectedSession={appState.selectedSession}
                onSessionSelect={handleSessionSelect}
              />
            </div>
          )}
          {appState.selectedThread && appState.selectedSession && (
            <div className="animate-fade-in">
              <FileExplorer
                threadId={appState.selectedThread}
                sessionId={appState.selectedSession}
                selectedFile={appState.selectedFile}
                onFileSelect={handleFileSelect}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <Layout sidebar={sidebar}>
      {renderMainContent()}
    </Layout>
  );
}

export default App;
