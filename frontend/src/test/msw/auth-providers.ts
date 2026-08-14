import { http, HttpResponse } from "msw";
import type { RequestHandler } from "msw";
import type { AuthProvidersResponse } from "@/shared/api/auth";

const PROVIDERS_URL = "/api/auth/providers";

// Фабрика MSW-хендлеров GET /api/auth/providers. В default handlers.ts не
// кладём (conventions: дефолтные хендлеры пусты) — каждый тест подключает
// нужный вариант через server.use(authProvidersHandlers.<variant>()).
export const authProvidersHandlers = {
  // РФ-гео: серверный enforcement пропускает только Яндекс.
  ru: (): RequestHandler =>
    http.get(PROVIDERS_URL, () =>
      HttpResponse.json<AuthProvidersResponse>({
        providers: ["yandex"],
        password: true,
      }),
    ),
  // Не-РФ-гео: все активные провайдеры.
  nonRu: (): RequestHandler =>
    http.get(PROVIDERS_URL, () =>
      HttpResponse.json<AuthProvidersResponse>({
        providers: ["yandex", "google", "github"],
        password: true,
      }),
    ),
  // Запрос упал — блок кнопок провайдеров деградирует, парольный вход остаётся.
  failure: (): RequestHandler =>
    http.get(PROVIDERS_URL, () =>
      HttpResponse.json({ detail: "Internal Server Error" }, { status: 500 }),
    ),
};
