import React from 'react';
import { Download, Share2, ExternalLink, FileText, Calendar } from 'lucide-react';

interface DocumentHeaderProps {
  filename: string;
  threadId?: string;
  sessionId?: string;
  fileSize?: number;
  modifiedDate?: string;
  onExport?: () => void;
  onShare?: () => void;
  onOpenExternal?: () => void;
  className?: string;
}

export const DocumentHeader: React.FC<DocumentHeaderProps> = ({
  filename,
  threadId,
  sessionId,
  fileSize,
  modifiedDate,
  onExport,
  onShare,
  onOpenExternal,
  className = ''
}) => {
  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className={`animate-fade-in ${className}`}>
      {/* Main Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="status-dot-success flex-shrink-0"></div>
          <div className="flex-1 min-w-0">
            <h1 className="display-h2 truncate">
              {filename}
            </h1>
            
            {/* File metadata */}
            <div className="flex items-center gap-2 mt-2 text-xs">
              <span className="caption-text text-muted flex items-center gap-1">
                <FileText className="w-3 h-3" />
                Document
              </span>
              {fileSize && (
                <>
                  <span className="caption-text text-muted">•</span>
                  <span className="caption-text text-muted">
                    {formatFileSize(fileSize)}
                  </span>
                </>
              )}
              {modifiedDate && (
                <>
                  <span className="caption-text text-muted">•</span>
                  <span className="caption-text text-muted flex items-center gap-1">
                    <Calendar className="w-3 h-3" />
                    {formatDate(modifiedDate)}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 flex-shrink-0 ml-4">
          {onExport && (
            <button
              onClick={onExport}
              className="btn-ghost btn-sm"
              title="Export document"
            >
              <Download className="w-4 h-4" />
              <span className="ml-2 hidden sm:inline">Export</span>
            </button>
          )}
          {onShare && (
            <button
              onClick={onShare}
              className="btn-ghost btn-sm"
              title="Share document"
            >
              <Share2 className="w-4 h-4" />
              <span className="ml-2 hidden sm:inline">Share</span>
            </button>
          )}
          {onOpenExternal && (
            <button
              onClick={onOpenExternal}
              className="btn-ghost btn-sm"
              title="Open in new tab"
            >
              <ExternalLink className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Breadcrumb navigation */}
      {(threadId || sessionId) && (
        <div className="flex items-center gap-3 mb-6">
          {threadId && (
            <span className="chip-info">
              Thread: {threadId.slice(0, 8)}...
            </span>
          )}
          {sessionId && (
            <span className="chip-primary">
              Session: {sessionId.slice(0, 12)}...
            </span>
          )}
        </div>
      )}

      {/* Divider */}
      <div className="divider-horizontal"></div>
    </div>
  );
};