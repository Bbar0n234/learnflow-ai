import { type ChangeEvent, type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { login, register, useAuthProviders } from "@/shared/api/auth";
import { setAccessToken } from "@/shared/api/client";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";
import { LoginScreenView, type LoginMode } from "./LoginScreenView";
import { ProviderButtons } from "./ProviderButtons";
import { getActiveProviders } from "./provider-registry";

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

/**
 * Контейнер страницы входа. Логика формы перенесена из `AuthGate`
 * (парольный вход/регистрация, клиентская валидация); блок кнопок
 * провайдеров и переход на `/authorize` с транспортом `next`, обработка
 * `?error=` — T2.4.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  // `RequireAuth` кладёт исходный путь в `location.state.from` строкой
  // (`pathname + search + hash`); прямой заход на `/login` не несёт этого
  // состояния — дефолт `/`. Та же строка идёт в `next` кнопок провайдеров.
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  const { data: providersData } = useAuthProviders();
  const activeProviders = getActiveProviders(providersData?.providers ?? []);

  const [mode, setMode] = useState<LoginMode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  // Начальное значение — сообщение по коду `?error=` из query (возврат из
  // OAuth-флоу с отказом); одноразовое чтение при монтировании страницы,
  // дальше блок ошибки общий с парольной формой.
  const [error, setError] = useState(() => {
    const code = new URLSearchParams(location.search).get("error");
    return code ? getOAuthErrorMessage(code) : "";
  });
  const [loading, setLoading] = useState(false);

  function handleProviderSelect(providerId: string) {
    // Полная навигация браузера, не fetch: OAuth-флоу редиректный.
    const next = encodeURIComponent(from);
    window.location.assign(
      `/api/auth/oauth/${providerId}/authorize?next=${next}`,
    );
  }

  function handleNameChange(event: ChangeEvent<HTMLInputElement>) {
    setName(event.target.value);
  }

  function handlePasswordChange(event: ChangeEvent<HTMLInputElement>) {
    setPassword(event.target.value);
  }

  function handleConfirmPasswordChange(event: ChangeEvent<HTMLInputElement>) {
    setConfirmPassword(event.target.value);
  }

  function handleModeToggle() {
    setMode((prev) => (prev === "login" ? "register" : "login"));
    setError("");
    setConfirmPassword("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const trimmedName = name.trim();
    if (!trimmedName || !password) return;

    if (mode === "register") {
      if (password.length < 8) {
        setError("Пароль должен содержать не менее 8 символов");
        return;
      }
      if (password !== confirmPassword) {
        setError("Пароли не совпадают");
        return;
      }
    }

    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await login(trimmedName, password)
          : await register(trimmedName, password);
      setAccessToken(result.access_token);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
      logger.error("[LoginPage] auth error", err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <LoginScreenView
      mode={mode}
      name={name}
      password={password}
      confirmPassword={confirmPassword}
      onNameChange={handleNameChange}
      onPasswordChange={handlePasswordChange}
      onConfirmPasswordChange={handleConfirmPasswordChange}
      onSubmit={handleSubmit}
      onModeToggle={handleModeToggle}
      error={error}
      loading={loading}
      providersSlot={
        activeProviders.length > 0 ? (
          <ProviderButtons
            entries={activeProviders}
            onSelect={handleProviderSelect}
          />
        ) : undefined
      }
    />
  );
}
