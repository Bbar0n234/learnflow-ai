import React from 'react';
import { ChevronDown, ChevronRight, Folder, FolderOpen, File, User, Download } from 'lucide-react';
import type { Thread, Session, FileInfo } from '../services/types';
import { ConfigService } from '../services/ConfigService';
import { cn } from '../utils/cn';
import { useUrlDrivenExpansion } from '../hooks/useUrlDrivenExpansion';

interface AccordionSidebarProps {
  threads: Thread[];
  sessionFiles: Map<string, FileInfo[]>;
  selectedThread: string | null;
  selectedSession: string | null;
  selectedFile: string | null;
  onSelect: (thread: string, session?: string, file?: string) => void;
  onExportSession?: (threadId: string, sessionId: string) => void;
}

export const AccordionSidebar: React.FC<AccordionSidebarProps> = ({
  threads,
  sessionFiles,
  selectedThread,
  selectedSession,
  selectedFile,
  onSelect,
  onExportSession,
}) => {
  // Get expansion state from URL
  const expanded = useUrlDrivenExpansion();

  const renderFile = (file: FileInfo, threadId: string, sessionId: string, indent: number) => {
    const displayName = ConfigService.getDisplayName(file.path);
    const isSelected = selectedThread === threadId && 
                      selectedSession === sessionId && 
                      selectedFile === file.path;
    
    return (
      <div
        key={file.path}
        className={cn(
          'sidebar-item',
          isSelected && 'sidebar-item-active'
        )}
        style={{ paddingLeft: `${indent}px` }}
        onClick={() => onSelect(threadId, sessionId, file.path)}
      >
        <File className="w-3.5 h-3.5 mr-2 text-muted shrink-0" />
        <span className="text-sm truncate" title={displayName}>
          {displayName}
        </span>
      </div>
    );
  };

  const renderFiles = (files: FileInfo[], threadId: string, sessionId: string, indent: number) => {
    // Group files by folder
    const grouped = ConfigService.groupFilesByFolder(files.map(f => f.path));
    const elements: React.ReactNode[] = [];

    // Render root files first
    const rootFiles = grouped.get('root') || [];
    rootFiles.forEach(filePath => {
      const file = files.find(f => f.path === filePath);
      if (file) {
        elements.push(renderFile(file, threadId, sessionId, indent));
      }
    });

    // Render folders
    grouped.forEach((folderFiles, folder) => {
      if (folder === 'root') return;
      
      const folderId = `${threadId}-${sessionId}-${folder}`;
      const isExpanded = expanded.folders.has(folderId);
      const folderName = ConfigService.getFolderDisplayName(folder);
      
      elements.push(
        <div key={folder}>
          <div
            className="sidebar-item"
            style={{ paddingLeft: `${indent}px` }}
            onClick={(e) => {
              e.stopPropagation();
              // Navigate to the first file in the folder to trigger folder expansion
              if (folderFiles.length > 0) {
                const firstFilePath = folderFiles[0];
                const file = files.find(f => f.path === firstFilePath);
                if (file) {
                  onSelect(threadId, sessionId, file.path);
                }
              }
            }}
          >
            {isExpanded ? (
              <>
                <ChevronDown className="w-3 h-3 mr-1 text-muted" />
                <FolderOpen className="w-3.5 h-3.5 mr-2 text-muted" />
              </>
            ) : (
              <>
                <ChevronRight className="w-3 h-3 mr-1 text-muted" />
                <Folder className="w-3.5 h-3.5 mr-2 text-muted" />
              </>
            )}
            <span className="text-sm font-medium truncate">{folderName}</span>
            <span className="ml-auto text-xs text-muted">{folderFiles.length}</span>
          </div>
          
          {isExpanded && (
            <div>
              {folderFiles.map(filePath => {
                const file = files.find(f => f.path === filePath);
                if (file) {
                  return renderFile(file, threadId, sessionId, indent + 16);
                }
                return null;
              })}
            </div>
          )}
        </div>
      );
    });

    return elements;
  };

  const renderSession = (session: Session, thread: Thread, indent: number) => {
    const sessionKey = `${thread.thread_id}-${session.session_id}`;
    const isExpanded = expanded.sessions.has(sessionKey);
    const displayName = ConfigService.getSessionDisplayName(session);
    const files = sessionFiles.get(`${thread.thread_id}/${session.session_id}`) || [];
    const isSelected = selectedThread === thread.thread_id && selectedSession === session.session_id;
    
    return (
      <div key={session.session_id}>
        <div
          className={cn(
            'sidebar-item sidebar-section-header group',
            isSelected && !selectedFile && 'sidebar-item-active'
          )}
          style={{ 
            paddingLeft: `${indent}px`
          }}
          onClick={() => {
            onSelect(thread.thread_id, session.session_id);
          }}
        >
          {isExpanded ? (
            <ChevronDown className="w-3 h-3 mr-1 text-muted shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 mr-1 text-muted shrink-0" />
          )}
          <span className="text-sm font-medium truncate" title={displayName}>
            {displayName}
          </span>
          <div className="ml-auto flex items-center">
            {onExportSession && files.length > 0 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onExportSession(thread.thread_id, session.session_id);
                }}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors cursor-pointer opacity-0 group-hover:opacity-100"
                title="Экспортировать сессию"
                style={{ minWidth: '20px', minHeight: '20px', marginRight: '5px' }}
              >
                <Download className="w-3 h-3" />
              </button>
            )}
            <span className="text-xs text-muted shrink-0">{files.length > 0 ? files.length : session.files_count}</span>
          </div>
        </div>
        
        {isExpanded && files.length > 0 && (
          <div>
            {renderFiles(files, thread.thread_id, session.session_id, indent + 16)}
          </div>
        )}
      </div>
    );
  };

  const renderThread = (thread: Thread) => {
    const isExpanded = expanded.threads.has(thread.thread_id);
    const sessions = thread.sessions || [];
    const isSelected = selectedThread === thread.thread_id;
    
    // Deduplicate session names if needed
    const sessionNameMap = new Map<Session, string>();
    const nameCounts = new Map<string, number>();
    
    sessions.forEach(session => {
      const name = ConfigService.getSessionDisplayName(session);
      const count = nameCounts.get(name) || 0;
      nameCounts.set(name, count + 1);
      
      if (count === 0) {
        sessionNameMap.set(session, name);
      } else {
        sessionNameMap.set(session, `${name} (${count + 1})`);
      }
    });
    
    return (
      <div key={thread.thread_id} className="border-b border-border/5">
        <div
          className={cn(
            'sidebar-item sidebar-section-header',
            isSelected && !selectedSession && 'sidebar-item-active'
          )}
          onClick={() => {
            onSelect(thread.thread_id);
          }}
        >
          {isExpanded ? (
            <ChevronDown className="w-3 h-3 mr-1 text-muted shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 mr-1 text-muted shrink-0" />
          )}
          <User className="w-3.5 h-3.5 mr-2 text-muted shrink-0" />
          <span className="text-sm font-semibold truncate">
            Thread {thread.thread_id}
          </span>
          <span className="ml-auto text-xs text-muted shrink-0">
            {sessions.length}
          </span>
        </div>
        
        {isExpanded && (
          <div className="pb-2">
            {sessions.map(session => renderSession(session, thread, 24))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="accordion-sidebar">
      <div className="px-4 py-2 border-b border-border/10 bg-elev">
        <h2 className="text-xs font-semibold text-muted uppercase tracking-wider">
          Threads & Sessions
        </h2>
      </div>
      
      <div className="pb-4">
        {threads.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-muted">No threads available</p>
          </div>
        ) : (
          threads.map(thread => renderThread(thread))
        )}
      </div>
    </div>
  );
};