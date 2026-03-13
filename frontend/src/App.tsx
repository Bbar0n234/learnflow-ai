import { BrowserRouter } from "react-router";
import { AppRoutes } from "./app/router";

export function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
