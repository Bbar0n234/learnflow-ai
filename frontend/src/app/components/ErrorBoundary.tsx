import { Component, type ErrorInfo, type ReactNode } from "react";
import { logger } from "@/shared/lib/logger";
import { Button } from "@/shared/ui/button";
import { StateScreen } from "@/shared/ui/StateScreen";

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
        <StateScreen
          scene="error-state"
          alt="Иллюстрация: ошибка"
          illustrationClassName="max-w-[280px]"
          title="Что-то пошло не так"
          description="Произошла непредвиденная ошибка. Попробуйте обновить страницу."
          action={
            <Button variant="outline" onClick={() => window.location.reload()}>
              Обновить страницу
            </Button>
          }
          className="h-screen bg-background text-foreground"
        />
      );
    }

    return this.props.children;
  }
}
