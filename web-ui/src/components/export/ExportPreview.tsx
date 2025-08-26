import React from 'react';
import { FileText, Check, X } from 'lucide-react';

interface DocumentInfo {
  name: string;
  label: string;
  exists: boolean;
  size?: number;
}

interface ExportPreviewProps {
  documents: DocumentInfo[];
  format: 'markdown' | 'pdf';
  packageType?: 'final' | 'all';
}

export const ExportPreview: React.FC<ExportPreviewProps> = ({
  documents,
  format,
  packageType
}) => {
  const formatSize = (bytes?: number): string => {
    if (!bytes) return '';
    const kb = bytes / 1024;
    return kb > 1024 
      ? `${(kb / 1024).toFixed(1)} MB`
      : `${kb.toFixed(1)} KB`;
  };

  const totalSize = documents.reduce((acc, doc) => acc + (doc.size || 0), 0);

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
      <div className="mb-3">
        <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
          Документы для экспорта
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Формат: {format === 'pdf' ? 'PDF' : 'Markdown'}
          {packageType && ` • Пакет: ${packageType === 'all' ? 'Все документы' : 'Финальные'}`}
        </p>
      </div>

      <div className="space-y-2">
        {documents.map((doc) => (
          <div
            key={doc.name}
            className={`flex items-center justify-between p-2 rounded ${
              doc.exists
                ? 'bg-green-50 dark:bg-green-900/20'
                : 'bg-gray-50 dark:bg-gray-800'
            }`}
          >
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-gray-400" />
              <span className={`text-sm ${
                doc.exists 
                  ? 'text-gray-900 dark:text-gray-100' 
                  : 'text-gray-400 dark:text-gray-500'
              }`}>
                {doc.label}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {doc.size && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {formatSize(doc.size)}
                </span>
              )}
              {doc.exists ? (
                <Check className="w-4 h-4 text-green-500" />
              ) : (
                <X className="w-4 h-4 text-gray-300" />
              )}
            </div>
          </div>
        ))}
      </div>

      {totalSize > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex justify-between text-sm">
            <span className="text-gray-600 dark:text-gray-400">
              Примерный размер:
            </span>
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {formatSize(totalSize)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};