import React, { useState } from 'react';
import { ThemeToggle } from './ThemeToggle';
import { UserIndicator } from './auth/UserIndicator';
import { Menu, X } from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
  sidebar?: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children, sidebar }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="h-screen overflow-hidden bg-bg transition-colors duration-200">
      {/* Minimal Header */}
      <header className="sticky top-0 z-30 bg-elev/80 backdrop-blur-sm px-4 py-0 border-b border-border/60" style={{ height: 'var(--header-height)' }}>
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
            
            <div className="flex items-center gap-3 group cursor-pointer transition-all duration-200 hover:opacity-90">
              <img 
                src="/square_logo_without_bg.png" 
                alt="LearnFlow AI Logo" 
                className="w-[56px] h-[56px] object-contain transition-transform duration-200 group-hover:scale-105"
              />
              <div className="leading-tight">
                <h1 className="font-display text-[24px] font-semibold leading-6 tracking-wide transition-colors duration-200">
                  <span className="text-ink group-hover:text-primary/90">LearnFlow</span> <span className="text-primary group-hover:text-primary/80">AI</span>
                </h1>
                <p className="text-[14px] text-muted transition-colors duration-200 group-hover:text-muted/80">Artifacts Viewer</p>
              </div>
            </div>
          </div>
          <div className="header-actions">
            <UserIndicator />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <div className="flex" style={{ height: 'calc(100vh - var(--header-height))' }}>
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
            <aside className={`sidebar-container scrollbar-thin ${sidebarOpen ? 'sidebar-mobile open' : 'sidebar-mobile'}`}>
              {sidebar}
            </aside>
          </>
        )}

        {/* Main Content */}
        <main className="main-content scrollbar-thin">
          <div className="content-container py-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};