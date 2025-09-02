import { useState } from 'react';
import { apiClient } from '../services/ApiClient';
import type { ExportFormat, PackageType } from '../types/export';
import type { FileInfo } from '../services/types';

interface UseExportReturn {
  exportSingleDocument: (
    threadId: string,
    sessionId: string,
    documentName: string,
    format: ExportFormat
  ) => Promise<void>;
  exportPackage: (
    threadId: string,
    sessionId: string,
    packageType: PackageType,
    format: ExportFormat
  ) => Promise<void>;
  getAvailableDocuments: (sessionFiles: FileInfo[]) => string[];
  isLoading: boolean;
  error: string | null;
}

export function useExport(): UseExportReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  };

  const exportSingleDocument = async (
    threadId: string,
    sessionId: string,
    documentName: string,
    format: ExportFormat
  ): Promise<void> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const blob = await apiClient.exportSingleDocument(
        threadId,
        sessionId,
        documentName,
        format
      );
      // Generate timestamp for unique filename
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const baseName = documentName.replace(/\.[^/.]+$/, '');
      const filename = `${baseName}_${timestamp}.${format === 'pdf' ? 'pdf' : 'md'}`;
      downloadBlob(blob, filename);
    } catch (err) {
      let errorMessage = 'Ошибка при экспорте документа';
      
      if (err instanceof Error) {
        // Check for timeout error
        if (err.message.includes('timeout') || err.message.includes('ECONNABORTED')) {
          errorMessage = 'Превышено время ожидания. Попробуйте использовать формат Markdown вместо PDF для более быстрого экспорта.';
        } else if (err.message.includes('Network Error')) {
          errorMessage = 'Ошибка сети. Проверьте подключение к интернету и попробуйте снова.';
        } else {
          errorMessage = err.message;
        }
      }
      
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const exportPackage = async (
    threadId: string,
    sessionId: string,
    packageType: PackageType,
    format: ExportFormat
  ): Promise<void> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const blob = await apiClient.exportPackage(
        threadId,
        sessionId,
        packageType,
        format
      );
      // Generate timestamp for unique filename
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      // Package export always returns a ZIP archive containing documents in the requested format
      const sessionShort = sessionId.slice(0, 8);
      const filename = `session_${sessionShort}_${packageType}_${format}_${timestamp}.zip`;
      downloadBlob(blob, filename);
    } catch (err) {
      let errorMessage = 'Ошибка при экспорте пакета';
      
      if (err instanceof Error) {
        // Check for timeout error
        if (err.message.includes('timeout') || err.message.includes('ECONNABORTED')) {
          errorMessage = 'Превышено время ожидания. Экспорт большого пакета может занимать больше времени. Попробуйте экспортировать меньший пакет или использовать формат Markdown вместо PDF.';
        } else if (err.message.includes('Network Error')) {
          errorMessage = 'Ошибка сети. Проверьте подключение к интернету и попробуйте снова.';
        } else {
          errorMessage = err.message;
        }
      }
      
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  const getAvailableDocuments = (sessionFiles: FileInfo[]): string[] => {
    const exportableExtensions = ['.md', '.txt', '.json'];
    
    return sessionFiles
      .filter(file => {
        const hasExportableExtension = exportableExtensions.some(ext => 
          file.path.toLowerCase().endsWith(ext)
        );
        return hasExportableExtension;
      })
      .map(file => file.path);
  };

  return {
    exportSingleDocument,
    exportPackage,
    getAvailableDocuments,
    isLoading,
    error
  };
}