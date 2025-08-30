import React from 'react';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';

export const UserIndicator: React.FC = () => {
  const { isAuthenticated, currentUser, logout } = useAuth();

  if (!isAuthenticated || !currentUser) {
    return null;
  }

  return (
    <div className="user-profile-section">
      {/* Vertical divider */}
      <div className="user-profile-divider" />
      
      {/* User info */}
      <div className="user-profile-info">
        <div className="user-avatar">
          {currentUser.username.slice(0, 2).toUpperCase()}
        </div>
        <span className="user-name">
          {currentUser.username}
        </span>
      </div>
      
      {/* Logout button */}
      <button
        onClick={logout}
        className="user-action-btn logout-btn"
        aria-label="Выйти"
        title="Выйти"
      >
        <LogOut className="w-4 h-4" />
        <span className="logout-btn-text">Выйти</span>
      </button>
    </div>
  );
};