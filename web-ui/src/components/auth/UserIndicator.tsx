import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { Button } from '../ui';

export const UserIndicator: React.FC = () => {
  const { isAuthenticated, currentUser, logout } = useAuth();

  if (!isAuthenticated || !currentUser) {
    return null;
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-semibold text-sm">
          {currentUser.username.slice(0, 2).toUpperCase()}
        </div>
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          {currentUser.username}
        </span>
      </div>
      <Button
        onClick={logout}
        variant="ghost"
        size="sm"
        className="text-red-600 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
      >
        Выйти
      </Button>
    </div>
  );
};