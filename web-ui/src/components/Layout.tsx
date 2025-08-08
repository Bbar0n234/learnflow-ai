import React, { useState } from 'react';
import { ThemeToggle } from './ThemeToggle';
import { BookOpen, Menu, X } from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
  sidebar?: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children, sidebar }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-bg transition-colors duration-200">
      {/* Minimal Header */}
      <header className="sticky top-0 z-30 bg-elev/80 backdrop-blur-sm px-4 py-0" style={{ height: 'var(--header-height)' }}>
        <div className="flex items-center justify-between max-w-content mx-auto h-full">
          <div className="flex items-center gap-4">
            {/* Mobile sidebar toggle */}
            {sidebar && (
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="btn-ghost btn-sm md:hidden"
                aria-label="Toggle navigation"
              >
                {sidebarOpen ? (
                  <X className="w-4 h-4" />
                ) : (
                  <Menu className="w-4 h-4" />
                )}
              </button>
            )}
            
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-primary rounded-sm flex items-center justify-center shadow-sm">
                <BookOpen className="w-4 h-4 text-primary-ink" />
              </div>
              <div className="leading-tight">
                <h1 className="font-display text-[18px] leading-5 tracking-wide">
                  <span className="text-ink">LearnFlow</span> <span className="text-primary">AI</span>
                </h1>
                <p className="text-[12px] text-muted">Artifacts Viewer</p>
              </div>
            </div>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="flex">
        {/* Sidebar */}
        {sidebar && (
          <>
            {/* Mobile overlay */}
            {sidebarOpen && (
              <div 
                className="sidebar-overlay"
                onClick={() => setSidebarOpen(false)}
              />
            )}
            
            {/* Sidebar container */}
            <aside className={`sidebar-container ${sidebarOpen ? 'sidebar-mobile open' : 'sidebar-mobile'}`}>
              <div className="h-full overflow-y-auto scrollbar-thin py-4">
                {sidebar}
              </div>
            </aside>
          </>
        )}

        {/* Main Content */}
        <main className="main-content">
          <div className="content-container min-h-[calc(100vh-var(--header-height))] py-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};