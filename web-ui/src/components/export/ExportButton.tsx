import React from 'react';
import { Download } from 'lucide-react';
import { Button } from '../ui';

interface ExportButtonProps {
  onClick: () => void;
  loading?: boolean;
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const ExportButton: React.FC<ExportButtonProps> = ({
  onClick,
  loading = false,
  variant = 'secondary',
  size = 'md',
  className = ''
}) => {
  return (
    <Button
      onClick={onClick}
      variant={variant}
      size={size}
      disabled={loading}
      className={`flex items-center gap-2 ${className}`}
    >
      <Download className="w-4 h-4" />
      {loading ? 'Экспортируем...' : 'Экспорт'}
    </Button>
  );
};