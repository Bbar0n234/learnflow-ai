import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppWithRouter from './AppWithRouter';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { AuthGuard } from './components/auth/AuthGuard';
import { LoginPage } from './components/auth/LoginPage';

export const RouterWrapper = () => {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <Routes>
            {/* Login route - no auth required */}
            <Route path="/login" element={<LoginPage />} />
            
            {/* Protected routes - require authentication */}
            <Route path="/" element={
              <AuthGuard requireAuth={true}>
                <AppWithRouter />
              </AuthGuard>
            } />
            <Route path="/thread/:threadId" element={
              <AuthGuard requireAuth={true} validateOwnership={true}>
                <AppWithRouter />
              </AuthGuard>
            } />
            <Route path="/thread/:threadId/session/:sessionId" element={
              <AuthGuard requireAuth={true} validateOwnership={true}>
                <AppWithRouter />
              </AuthGuard>
            } />
            <Route path="/thread/:threadId/session/:sessionId/file/*" element={
              <AuthGuard requireAuth={true} validateOwnership={true}>
                <AppWithRouter />
              </AuthGuard>
            } />
            
            {/* Fallback route */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};