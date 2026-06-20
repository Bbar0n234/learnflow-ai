import { Component, type ErrorInfo, type ReactNode } from "react";
import { logger } from "@/shared/lib/logger";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    logger.error("render error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background text-foreground">
          <h1 className="text-2xl font-semibold">Что-то пошло не так</h1>
          <p className="text-muted-foreground">
            Произошла непредвиденная ошибка.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="rounded-lg border border-border bg-card px-4 py-2 text-base text-foreground hover:bg-muted"
          >
            Обновить страницу
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
