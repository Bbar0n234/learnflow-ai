import React, { useEffect, useState } from 'react';
import { FileText, Calendar, Download } from 'lucide-react';
import type { Session } from '../services/types';
import { apiClient } from '../services/ApiClient';
import { useApi } from '../hooks/useApi';
import { ExportDialog } from './export';
import type { ExportFormat, PackageType } from './export';

interface SessionsListProps {
  threadId: string | null;
  selectedSession: string | null;
  onSessionSelect: (sessionId: string) => void;
}

export const SessionsList: React.FC<SessionsListProps> = ({ 
  threadId, 
  selectedSession, 
  onSessionSelect 
}) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportingSession, setExportingSession] = useState<string | null>(null);
  const { isLoading, error, executeRequest } = useApi();

  useEffect(() => {
    if (threadId) {
      loadSessions();
    } else {
      setSessions([]);
    }
  }, [threadId]);

  const loadSessions = async () => {
    if (!threadId) return;
    
    const result = await executeRequest(apiClient.getThread(threadId));
    if (result && result.sessions) {
      setSessions(result.sessions);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const handleExport = async (format: ExportFormat, packageType: PackageType) => {
    if (!threadId || !exportingSession) return;
    
    try {
      const blob = await apiClient.exportPackage(threadId, exportingSession, packageType, format);
      const filename = `session_${exportingSession}_export.${packageType === 'final' ? 'final' : 'all'}.zip`;
      apiClient.downloadBlob(blob, filename);
      setExportDialogOpen(false);
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  const openExportDialog = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExportingSession(sessionId);
    setExportDialogOpen(true);
  };

  if (!threadId) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Sessions</div>
        <div className="px-3 py-6 text-center text-muted text-xs">
          Select a thread to view sessions
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Sessions</div>
        <div className="space-y-1">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="sidebar-item">
              <div className="skeleton-avatar"></div>
              <div className="flex-1">
                <div className="skeleton-text mb-1"></div>
                <div className="skeleton-text w-2/3"></div>
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
        <div className="sidebar-section-header">Sessions</div>
        <div className="px-3 py-6 text-center">
          <div className="text-danger mb-2 text-sm">
            Failed to load sessions
          </div>
          <button
            onClick={loadSessions}
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
        <span>Sessions</span>
        <span className="chip-default text-[11px] h-4 px-1">
          {sessions.length}
        </span>
      </div>
      
      {sessions.length === 0 ? (
        <div className="px-3 py-8 text-center text-muted">
          <FileText className="h-6 w-6 mx-auto mb-2 opacity-50" />
          <p className="text-xs">No sessions found</p>
        </div>
      ) : (
        <div className="space-y-1">
          {sessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => onSessionSelect(session.session_id)}
              className={`sidebar-item ${
                selectedSession === session.session_id ? 'active' : ''
              }`}
            >
              <div className="sidebar-item-icon">
                <FileText className="w-4 h-4" />
              </div>
              <div className="sidebar-item-text">
                <div className="font-medium truncate">
                  {session.session_id.slice(0, 16)}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                  <div className="flex items-center gap-1 truncate">
                    <Calendar className="w-3 h-3" />
                    <span className="truncate" title={`Created: ${formatDate(session.created)}`}>
                      {formatDate(session.created)}
                    </span>
                  </div>
                </div>
              </div>
              <div className="sidebar-item-meta flex items-center gap-1">
                <span>{session.files_count}</span>
                <button
                  onClick={(e) => openExportDialog(session.session_id, e)}
                  className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded"
                  title="Export session"
                >
                  <Download className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      
      <ExportDialog
        isOpen={exportDialogOpen}
        onClose={() => setExportDialogOpen(false)}
        onExport={handleExport}
        availableDocuments={['synthesized_material', 'questions', 'generated_material', 'recognized_notes']}
      />
    </div>
  );
};