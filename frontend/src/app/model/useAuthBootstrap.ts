import { useQuery } from "@tanstack/react-query";
import { getAccessToken, setAccessToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";

interface RefreshResponseBody {
  access_token: string;
}

// Единственный тихий бутстрап на все пути входа в SPA. Идёт мимо `apiClient`
// (стык feat-013, `shared/api/client.ts` — только чтение): его интерцептор
// безусловно пишет `logger.error` на 401, а 401 здесь — ожидаемый путь
// анонима, не ошибка. `refresh()` из `shared/api/auth.ts` по той же причине
// не используется — он ходит через `apiClient`.
//
// `queryFn` намеренно никогда не реджектится на 401/сетевой отказ: оба тихо
// завершаются анонимом, поэтому глобальный `QueryCache.onError`
// (app/providers/QueryProvider.tsx) на тихом пути не срабатывает.
//
// Единственный наблюдаемый результат — побочный эффект `setAccessToken`;
// статус аутентификации никто не читает (см. доккомментарий хука), поэтому
// возвращать нечего. `null` вместо `undefined` — требование TanStack Query:
// `queryFn`, вернувшая `undefined`, считается ошибкой.
async function bootstrapAuth(): Promise<null> {
  if (getAccessToken()) return null;

  const baseUrl = import.meta.env.VITE_API_URL ?? "/api";

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // Сеть недоступна — тот же тихий путь анонима, что и явный 401.
    return null;
  }

  if (!response.ok) return null;

  const data = (await response.json()) as RefreshResponseBody;
  setAccessToken(data.access_token);
  return null;
}

/**
 * Однократный app-уровневый бутстрап аутентификации (`App.tsx`): есть access
 * в localStorage → `ready` сразу; иначе — один тихий `POST /api/auth/refresh`,
 * который заодно подхватывает refresh-cookie, только что поставленную
 * OAuth-callback'ом.
 *
 * Отдаёт только `ready` — не статус аутентификации: бутстрап гейтит
 * монтирование маршрутов целиком (`App.tsx` не рендерит `AppRoutes`, пока не
 * готов), а вердикт «пускать или на `/login`» после этого принимает
 * `RequireAuth` синхронным чтением токена. Дедупликация повторного вызова
 * эффектов в `StrictMode` — на уровне TanStack Query: один query-ключ,
 * `retry: false`, бесконечные `staleTime`/`gcTime`.
 */
export function useAuthBootstrap(): { ready: boolean } {
  const { isPending } = useQuery({
    queryKey: queryKeys.auth.bootstrap,
    queryFn: bootstrapAuth,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  return { ready: !isPending };
}
