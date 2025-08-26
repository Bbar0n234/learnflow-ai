import React from 'react';
import { Loader2 } from 'lucide-react';

interface ExportProgressProps {
  progress?: number;
  message?: string;
}

export const ExportProgress: React.FC<ExportProgressProps> = ({
  progress,
  message = 'Подготовка экспорта...'
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8">
      <Loader2 className="w-8 h-8 animate-spin text-blue-500 mb-4" />
      
      {progress !== undefined && (
        <div className="w-full max-w-xs mb-4">
          <div className="bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}
      
      <p className="text-sm text-gray-600 dark:text-gray-400">
        {message}
      </p>
    </div>
  );
};