import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppWithRouter from './AppWithRouter';

export const RouterWrapper = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppWithRouter />} />
        <Route path="/thread/:threadId" element={<AppWithRouter />} />
        <Route path="/thread/:threadId/session/:sessionId" element={<AppWithRouter />} />
        <Route path="/thread/:threadId/session/:sessionId/file/*" element={<AppWithRouter />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};