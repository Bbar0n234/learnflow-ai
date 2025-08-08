import React, { useEffect, useState } from 'react';
import { File, FileText, Code, Download, Clock, AlertCircle } from 'lucide-react';
import type { FileInfo } from '../services/types';
import { apiClient } from '../services/ApiClient';
import { useApi } from '../hooks/useApi';

interface FileExplorerProps {
  threadId: string | null;
  sessionId: string | null;
  selectedFile: string | null;
  onFileSelect: (filePath: string) => void;
}

export const FileExplorer: React.FC<FileExplorerProps> = ({ 
  threadId, 
  sessionId, 
  selectedFile, 
  onFileSelect 
}) => {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const { isLoading, error, executeRequest } = useApi();

  useEffect(() => {
    if (threadId && sessionId) {
      loadFiles();
    } else {
      setFiles([]);
    }
  }, [threadId, sessionId]);

  const loadFiles = async () => {
    if (!threadId || !sessionId) return;
    
    const result = await executeRequest(apiClient.getSessionFiles(threadId, sessionId));
    if (result) {
      setFiles(result.files);
    }
  };

  const getFileIcon = (file: FileInfo) => {
    const ext = file.path?.toLowerCase().split('.').pop();
    
    switch (ext) {
      case 'md':
      case 'markdown':
        return <FileText className="h-4 w-4 text-primary" />;
      case 'json':
      case 'js':
      case 'ts':
      case 'py':
        return <Code className="h-4 w-4 text-success" />;
      default:
        return <File className="h-4 w-4 text-muted" />;
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const isPreviewable = (file: FileInfo) => {
    const ext = file.path?.toLowerCase().split('.').pop();
    return ['md', 'markdown', 'txt', 'json'].includes(ext || '');
  };

  if (!threadId || !sessionId) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Files</div>
        <div className="px-3 py-6 text-center text-muted text-xs">
          Select a session to view files
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="sidebar-section">
        <div className="sidebar-section-header">Files</div>
        <div className="space-y-1">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="sidebar-item">
              <div className="skeleton-avatar"></div>
              <div className="flex-1">
                <div className="skeleton-text mb-1"></div>
                <div className="skeleton-text w-1/2"></div>
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
        <div className="sidebar-section-header">Files</div>
        <div className="px-3 py-6 text-center">
          <div className="text-danger mb-2 text-sm">
            Failed to load files
          </div>
          <button
            onClick={loadFiles}
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
        <span>Files</span>
        <span className="chip-default text-[11px] h-4 px-1">
          {files.length}
        </span>
      </div>
      
      {files.length === 0 ? (
        <div className="px-3 py-8 text-center text-muted">
          <File className="h-6 w-6 mx-auto mb-2 opacity-50" />
          <p className="text-xs">No files found</p>
        </div>
      ) : (
        <div className="space-y-1">
          {files.map((file) => (
            <div
              key={file.path}
              onClick={() => isPreviewable(file) && onFileSelect(file.path)}
              className={`sidebar-item ${
                selectedFile === file.path ? 'active' : ''
              } ${
                !isPreviewable(file) ? 'opacity-60 cursor-not-allowed' : ''
              }`}
            >
              <div className="sidebar-item-icon">
                {getFileIcon(file)}
              </div>
              <div className="sidebar-item-text">
                <div className="font-medium truncate">
                  {file.path?.split('/').pop() || file.path}
                </div>
                <div className="flex items-center gap-2 mt-1 text-xs text-muted">
                  <div className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(file.modified)}
                  </div>
                  <span className="text-muted">•</span>
                  <span>{formatFileSize(file.size)}</span>
                </div>
                {!isPreviewable(file) && (
                  <div className="flex items-center gap-1 mt-1 text-xs text-warn">
                    <AlertCircle className="w-3 h-3" />
                    Preview unavailable
                  </div>
                )}
              </div>
              {!isPreviewable(file) && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    console.log('Download file:', file.path);
                  }}
                  className="btn-ghost p-1 opacity-0 group-hover:opacity-100"
                  title="Download file"
                >
                  <Download className="w-3 h-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};