import { type ReactNode } from "react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { AxiosError } from "axios";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

/**
 * Предикат ретраев для queries:
 * - 4xx — не ретраить (клиентская ошибка, повтор не поможет).
 * - 5xx / сеть — bounded retry (≤2, согласовано с backend max_retries=2, D-ERR-9).
 * - Мутации — retry: false (побочные эффекты без ключа идемпотентности не повторяем).
 */
function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof AxiosError && error.response) {
    const { status } = error.response;
    if (status >= 400 && status < 500) return false;
  }
  return failureCount < 2;
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: shouldRetryQuery,
    },
    mutations: {
      retry: false,
    },
  },
  queryCache: new QueryCache({
    onError: (error) => {
      const message = getApiErrorMessage(error);
      logger.error("[QueryCache]", message);
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      const message = getApiErrorMessage(error);
      logger.error("[MutationCache]", message);
      toast.error(message);
    },
  }),
});

export function QueryProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
