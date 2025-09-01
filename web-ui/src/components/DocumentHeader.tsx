import React from 'react';
import { Download } from 'lucide-react';

interface DocumentHeaderProps {
  filename: string;
  onExport?: () => void;
}

export const DocumentHeader: React.FC<DocumentHeaderProps> = ({ filename, onExport }) => {
  const displayName = filename.split('/').pop() || filename;
  
  return (
    <div className="document-header">
      <h2 className="document-header-title">
        {displayName}
      </h2>
      {onExport && (
        <button
          onClick={onExport}
          className="document-header-export-btn"
          title="Экспортировать документ"
        >
          <Download className="w-5 h-5" />
          <span>Экспорт</span>
        </button>
      )}
    </div>
  );
};