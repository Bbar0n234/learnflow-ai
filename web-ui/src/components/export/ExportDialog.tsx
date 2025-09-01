import React, { useState } from 'react';
import ReactDOM from 'react-dom';
import { X, FileText, FileArchive, Download } from 'lucide-react';
import type { ExportFormat, PackageType } from '../../types/export';

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

  if (!isOpen) {
    return null;
  }
  

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

  const dialogContent = (
    <>
      {/* Backdrop */}
      <div 
        className="export-dialog-backdrop" 
        onClick={onClose}
      />
      
      {/* Dialog */}
      <div className="export-dialog-container">
        <div className="export-dialog-content">
        {/* Header */}
        <div className="export-dialog-header">
          <h2 className="export-dialog-title">
            Экспорт документов
          </h2>
          <button
            onClick={onClose}
            className="export-dialog-close-btn"
            disabled={loading}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Export Mode Selection */}
        <div className="export-dialog-section">
          <label className="export-dialog-label">
            Режим экспорта
          </label>
          <div className="export-dialog-mode-buttons">
            <button
              onClick={() => setExportMode('package')}
              className={`export-dialog-mode-btn ${exportMode === 'package' ? 'active' : ''}`}
              disabled={loading}
            >
              <FileArchive className="w-5 h-5" />
              <span>Пакет документов</span>
            </button>
            <button
              onClick={() => setExportMode('single')}
              className={`export-dialog-mode-btn ${exportMode === 'single' ? 'active' : ''}`}
              disabled={loading}
            >
              <FileText className="w-5 h-5" />
              <span>Один документ</span>
            </button>
          </div>
        </div>

        {/* Package Type Selection (for package mode) */}
        {exportMode === 'package' && (
          <div className="export-dialog-section">
            <label className="export-dialog-label">
              Тип пакета
            </label>
            <select
              value={packageType}
              onChange={(e) => setPackageType(e.target.value as PackageType)}
              className="export-dialog-select"
              disabled={loading}
            >
              <option value="final">Финальные документы</option>
              <option value="all">Все документы</option>
            </select>
          </div>
        )}

        {/* Document Selection (for single mode) */}
        {exportMode === 'single' && (
          <div className="export-dialog-section">
            <label className="export-dialog-label">
              Выберите документ
            </label>
            <select
              value={selectedDocument}
              onChange={(e) => setSelectedDocument(e.target.value)}
              className="export-dialog-select"
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
        <div className="export-dialog-section">
          <label className="export-dialog-label">
            Формат экспорта
          </label>
          <div className="export-dialog-format-buttons">
            <button
              onClick={() => setFormat('markdown')}
              className={`export-dialog-format-btn ${format === 'markdown' ? 'active' : ''}`}
              disabled={loading}
            >
              <FileText className="w-4 h-4" />
              <span>Markdown</span>
            </button>
            <button
              onClick={() => setFormat('pdf')}
              className={`export-dialog-format-btn ${format === 'pdf' ? 'active' : ''}`}
              disabled={loading}
            >
              <FileText className="w-4 h-4" />
              <span>PDF</span>
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="export-dialog-actions">
          <button
            onClick={onClose}
            className="export-dialog-action-btn export-dialog-action-btn-secondary"
            disabled={loading}
          >
            Отмена
          </button>
          <button
            onClick={handleExport}
            className="export-dialog-action-btn export-dialog-action-btn-primary"
            disabled={loading || (exportMode === 'single' && !selectedDocument)}
          >
            <Download className="w-4 h-4" />
            {loading ? 'Экспортируем...' : 'Экспортировать'}
          </button>
        </div>
      </div>
      </div>
    </>
  );
  
  return ReactDOM.createPortal(dialogContent, document.body);
};