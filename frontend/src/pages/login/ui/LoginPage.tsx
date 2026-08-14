import { useState } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  LoginScreenView,
  type AuthFormValues,
  type AuthMode,
  type AuthProvider,
} from "@/features/auth";
import { login, register, useAuthProviders } from "@/shared/api/auth";
import { setAccessToken } from "@/shared/api/client";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

// Закрытый реестр кодов `/login?error=` (design-brief.md § Эндпоинты,
// таблица кодов) — тексты дословно из брифа. Неизвестный код → generic-текст
// `oauth_failed`.
type OAuthErrorCode =
  | "access_denied"
  | "flow_expired"
  | "provider_not_available_in_region"
  | "provider_unavailable"
  | "oauth_failed";

const OAUTH_ERROR_MESSAGES: Record<OAuthErrorCode, string> = {
  access_denied: "Вход отменён. Можно попробовать ещё раз или войти с паролем",
  flow_expired: "Сессия входа истекла — попробуйте ещё раз",
  provider_not_available_in_region:
    "Этот способ входа недоступен в вашем регионе",
  provider_unavailable: "Сервис входа временно недоступен — попробуйте позже",
  oauth_failed: "Не удалось войти — попробуйте ещё раз",
};

function isOAuthErrorCode(value: string): value is OAuthErrorCode {
  return value in OAUTH_ERROR_MESSAGES;
}

function getOAuthErrorMessage(code: string): string {
  return isOAuthErrorCode(code)
    ? OAUTH_ERROR_MESSAGES[code]
    : OAUTH_ERROR_MESSAGES.oauth_failed;
}

// Та же база, что `shared/api/client.ts` и `useAuthBootstrap.ts` — локальная
// константа, не импорт из client.ts (заморожен для этого трека).
const API_BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

// Эталонный порядок кнопок из мокапа (контракт `LoginScreenView.providers`):
// Яндекс → Google → GitHub, независимо от порядка серверного массива.
// Позитивный предикат по построению: неизвестный серверный id не встречается
// в реестре и не рендерится.
const PROVIDER_ORDER: readonly AuthProvider[] = ["yandex", "google", "github"];

const EMPTY_FORM: AuthFormValues = {
  name: "",
  password: "",
  confirmPassword: "",
};

/**
 * Контейнер страницы входа. Логика формы перенесена из `AuthGate`
 * (парольный вход/регистрация, клиентская валидация); дополнена блоком
 * кнопок провайдеров, переходом на `/authorize` с транспортом `next` и
 * обработкой `?error=`. Презентация — `features/auth` `LoginScreenView`
 * (AuthLayout + брендовые кнопки провайдеров); тексты клиентской валидации —
 * из его контракта, дословно.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  // `RequireAuth` кладёт исходный путь в `location.state.from` строкой
  // (`pathname + search + hash`); прямой заход на `/login` не несёт этого
  // состояния — дефолт `/`. Та же строка идёт в `next` кнопок провайдеров.
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const providersQuery = useAuthProviders();
  const serverProviders = providersQuery.data?.providers;
  // Семантика контракта view: `undefined` — состав грузится (skeleton-плашка),
  // `[]` — блока нет. Отказ запроса деградирует до пустого состава: парольный
  // вход не должен умирать вместе с блоком провайдеров.
  const providers: readonly AuthProvider[] | undefined = providersQuery.isError
    ? []
    : serverProviders === undefined
      ? undefined
      : PROVIDER_ORDER.filter((id) => serverProviders.includes(id));

  const [mode, setMode] = useState<AuthMode>("login");
  const [values, setValues] = useState<AuthFormValues>(EMPTY_FORM);
  // Начальное значение — сообщение по коду `?error=` из query (возврат из
  // OAuth-флоу с отказом); одноразовое чтение при монтировании страницы,
  // дальше блок ошибки общий с парольной формой.
  const [error, setError] = useState(() => {
    const code = new URLSearchParams(location.search).get("error");
    return code ? getOAuthErrorMessage(code) : "";
  });
  const [submitting, setSubmitting] = useState(false);

  function handleProviderSelect(provider: AuthProvider) {
    // Полная навигация браузера, не fetch: OAuth-флоу редиректный.
    const next = encodeURIComponent(from);
    window.location.assign(
      `${API_BASE_URL}/auth/oauth/${provider}/authorize?next=${next}`,
    );
  }

  function handleFieldChange(field: keyof AuthFormValues, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  function handleModeChange(next: AuthMode) {
    setMode(next);
    setError("");
    setValues((prev) => ({ ...prev, confirmPassword: "" }));
  }

  async function handleSubmit() {
    setError("");

    const trimmedName = values.name.trim();
    if (!trimmedName || !values.password) {
      setError("Введите имя и пароль.");
      return;
    }

    if (mode === "register") {
      if (values.password.length < 8) {
        setError("Пароль должен содержать не менее 8 символов.");
        return;
      }
      if (values.password !== values.confirmPassword) {
        setError("Пароли не совпадают.");
        return;
      }
    }

    setSubmitting(true);
    try {
      const result =
        mode === "login"
          ? await login(trimmedName, values.password)
          : await register(trimmedName, values.password);
      setAccessToken(result.access_token);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
      logger.error("[LoginPage] auth error", err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <LoginScreenView
      mode={mode}
      onModeChange={handleModeChange}
      values={values}
      onFieldChange={handleFieldChange}
      onSubmit={handleSubmit}
      providers={providers}
      onProviderSelect={handleProviderSelect}
      error={error}
      submitting={submitting}
    />
  );
}
