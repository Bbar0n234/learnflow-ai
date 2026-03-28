import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Providers } from "./app/providers";
import { App } from "./App";
import "./index.css";
import "streamdown/styles.css";
import "katex/dist/katex.min.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Providers>
      <App />
    </Providers>
  </StrictMode>,
);
