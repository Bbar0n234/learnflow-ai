import { BrowserRouter } from "react-router";
import { AppRoutes } from "./app/router";
import { AuthGate } from "./app/components/AuthGate";

export function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthGate>
  );
}
