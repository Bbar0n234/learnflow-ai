import React, { useEffect, useState } from 'react';
import { Folder, Calendar } from 'lucide-react';
import type { Thread } from '../services/types';
import { apiClient } from '../services/ApiClient';
import { useApi } from '../hooks/useApi';

interface ThreadsListProps {
  selectedThread: string | null;
  onThreadSelect: (threadId: string) => void;
}

export const ThreadsList: React.FC<ThreadsListProps> = ({ 
  selectedThread, 
  onThreadSelect 
}) => {
  const [threads, setThreads] = useState<Thread[]>([]);
  const { isLoading, error, executeRequest } = useApi();

  useEffect(() => {
    loadThreads();
  }, []);

  const loadThreads = async () => {
    const result = await executeRequest(apiClient.getThreads());
    if (result) {
      setThreads(result.threads);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  if (isLoading) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Threads</div>
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="sidebar-item">
              <div className="skeleton-avatar"></div>
              <div className="flex-1">
                <div className="skeleton-text mb-1"></div>
                <div className="skeleton-text w-3/4"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Threads</div>
        <div className="px-3 py-6 text-center">
          <div className="text-danger mb-2 text-sm">
            Failed to load threads
          </div>
          <button
            onClick={loadThreads}
            className="btn-primary btn-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="sidebar-section">
      <div className="sidebar-section-header flex items-center justify-between">
        <span>Threads</span>
        <span className="chip-default text-[11px] h-4 px-1">
          {threads.length}
        </span>
      </div>
      
      {threads.length === 0 ? (
        <div className="px-3 py-8 text-center text-muted">
          <Folder className="h-6 w-6 mx-auto mb-2 opacity-50" />
          <p className="text-xs">No threads found</p>
        </div>
      ) : (
        <div className="space-y-1">
          {threads.map((thread) => (
            <div
              key={thread.thread_id}
              onClick={() => onThreadSelect(thread.thread_id)}
              className={`sidebar-item ${
                selectedThread === thread.thread_id ? 'active' : ''
              }`}
            >
              <div className="sidebar-item-icon">
                <Folder className="w-4 h-4" />
              </div>
              <div className="sidebar-item-text">
                <div className="font-medium truncate">
                  {thread.thread_id.slice(0, 12)}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                  <div className="flex items-center gap-1 truncate">
                    <Calendar className="w-3 h-3" />
                    <span className="truncate" title={`Created: ${formatDate(thread.created)}`}>
                      {formatDate(thread.created)}
                    </span>
                  </div>
                </div>
              </div>
              <div className="sidebar-item-meta">
                {thread.sessions_count}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};