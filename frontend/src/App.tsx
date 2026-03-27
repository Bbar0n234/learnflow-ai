import { BrowserRouter } from "react-router";
import { ErrorBoundary } from "./app/components/ErrorBoundary";
import { AppRoutes } from "./app/router";
import { AuthGate } from "./app/components/AuthGate";

export function App() {
  return (
    <ErrorBoundary>
      <AuthGate>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthGate>
    </ErrorBoundary>
  );
}
