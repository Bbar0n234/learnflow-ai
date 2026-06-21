import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Providers } from "./app/providers";
import { App } from "./App";
import "./index.css";
import "streamdown/styles.css";
import "katex/dist/katex.min.css";
// Eagerly initialize theme store so it syncs DOM class before first render
import "./stores/theme-store";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>,
);
