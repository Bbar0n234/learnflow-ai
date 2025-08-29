import React, { useState } from 'react';
import { X, FileText, FileArchive, Download } from 'lucide-react';
import { Button } from '../ui';

export type ExportFormat = 'markdown' | 'pdf';
export type PackageType = 'final' | 'all';

interface ExportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onExport: (format: ExportFormat, packageType: PackageType, singleDocument?: string) => void;
  availableDocuments?: string[];
  loading?: boolean;
}

export const ExportDialog: React.FC<ExportDialogProps> = ({
  isOpen,
  onClose,
  onExport,
  availableDocuments = [],
  loading = false
}) => {
  const [exportMode, setExportMode] = useState<'single' | 'package'>('package');
  const [format, setFormat] = useState<ExportFormat>('markdown');
  const [packageType, setPackageType] = useState<PackageType>('final');
  const [selectedDocument, setSelectedDocument] = useState<string>('');

  if (!isOpen) return null;

  const handleExport = () => {
    if (exportMode === 'single' && selectedDocument) {
      onExport(format, packageType, selectedDocument);
    } else {
      onExport(format, packageType);
    }
  };

  const documentLabels: Record<string, string> = {
    'synthesized_material': 'Синтезированный материал',
    'questions': 'Вопросы для закрепления',
    'generated_material': 'Сгенерированный материал',
    'recognized_notes': 'Распознанные заметки'
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl p-6 w-full max-w-md">
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Экспорт документов
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            disabled={loading}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Export Mode Selection */}
        <div className="mb-4">
          <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
            Режим экспорта
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => setExportMode('package')}
              className={`flex-1 p-3 rounded-lg border-2 transition-colors ${
                exportMode === 'package'
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                  : 'border-gray-200 dark:border-gray-600'
              }`}
              disabled={loading}
            >
              <FileArchive className="w-5 h-5 mx-auto mb-1" />
              <span className="text-sm">Пакет документов</span>
            </button>
            <button
              onClick={() => setExportMode('single')}
              className={`flex-1 p-3 rounded-lg border-2 transition-colors ${
                exportMode === 'single'
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                  : 'border-gray-200 dark:border-gray-600'
              }`}
              disabled={loading}
            >
              <FileText className="w-5 h-5 mx-auto mb-1" />
              <span className="text-sm">Один документ</span>
            </button>
          </div>
        </div>

        {/* Package Type Selection (for package mode) */}
        {exportMode === 'package' && (
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
              Тип пакета
            </label>
            <select
              value={packageType}
              onChange={(e) => setPackageType(e.target.value as PackageType)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg 
                       bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              disabled={loading}
            >
              <option value="final">Финальные документы</option>
              <option value="all">Все документы</option>
            </select>
          </div>
        )}

        {/* Document Selection (for single mode) */}
        {exportMode === 'single' && (
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
              Выберите документ
            </label>
            <select
              value={selectedDocument}
              onChange={(e) => setSelectedDocument(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg 
                       bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              disabled={loading}
            >
              <option value="">-- Выберите документ --</option>
              {availableDocuments.map((doc) => (
                <option key={doc} value={doc}>
                  {documentLabels[doc] || doc}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Format Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium mb-2 text-gray-700 dark:text-gray-300">
            Формат экспорта
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => setFormat('markdown')}
              className={`flex-1 p-2 rounded-lg border-2 transition-colors ${
                format === 'markdown'
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                  : 'border-gray-200 dark:border-gray-600'
              }`}
              disabled={loading}
            >
              <span className="text-sm">📝 Markdown</span>
            </button>
            <button
              onClick={() => setFormat('pdf')}
              className={`flex-1 p-2 rounded-lg border-2 transition-colors ${
                format === 'pdf'
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30'
                  : 'border-gray-200 dark:border-gray-600'
              }`}
              disabled={loading}
            >
              <span className="text-sm">📄 PDF</span>
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-2">
          <Button
            variant="ghost"
            onClick={onClose}
            className="flex-1"
            disabled={loading}
          >
            Отмена
          </Button>
          <Button
            variant="primary"
            onClick={handleExport}
            className="flex-1 flex items-center justify-center gap-2"
            disabled={loading || (exportMode === 'single' && !selectedDocument)}
          >
            <Download className="w-4 h-4" />
            {loading ? 'Экспортируем...' : 'Экспортировать'}
          </Button>
        </div>
      </div>
    </div>
  );
};