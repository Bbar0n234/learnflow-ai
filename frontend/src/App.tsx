import { BrowserRouter } from "react-router";
import { ErrorBoundary } from "./app/components/ErrorBoundary";
import { AppRoutes } from "./app/router";
import { useAuthBootstrap } from "./app/model/useAuthBootstrap";

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-full">
    <p className="text-muted-foreground">Загрузка...</p>
  </div>
);

// Гейт над всем деревом маршрутов: пока однократный бутстрап аутентификации
// (`app/model/useAuthBootstrap.ts`) не завершён, роуты не смонтированы —
// показывается тот же паттерн загрузки, что у `SecurityRouteGuard`, не
// редирект. `RequireAuth` внутри `AppRoutes` принимает вердикт «пускать или
// на /login» уже после того, как этот гейт открылся.
function AppBootstrapGate() {
  const { ready } = useAuthBootstrap();

  if (!ready) return <LoadingFallback />;

  return <AppRoutes />;
}

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppBootstrapGate />
      </BrowserRouter>
    </ErrorBoundary>
  );
}
