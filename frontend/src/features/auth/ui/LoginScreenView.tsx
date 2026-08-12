import { useId, type FormEvent } from "react";

import { AuthLayout } from "@/shared/ui/AuthLayout";
import { ProviderButton, type AuthProvider } from "@/shared/ui/ProviderButton";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Skeleton } from "@/shared/ui/skeleton";
import { ErrorCard } from "@/shared/ui/StateScreen";

export type AuthMode = "login" | "register";

export interface AuthFormValues {
  name: string;
  password: string;
  /** Используется только в `mode="register"`. */
  confirmPassword: string;
}

export interface LoginScreenViewProps {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;

  values: AuthFormValues;
  onFieldChange: (field: keyof AuthFormValues, value: string) => void;

  /** Сабмит формы. View сам делает `preventDefault` и ничего не валидирует. */
  onSubmit: () => void;

  /**
   * Гео-состав кнопок провайдера решает потребитель (`features/auth` этот
   * гео не читает). Три состояния различаются семантически:
   * - `undefined` — состав ещё грузится (запрос гео не завершён): место под
   *   блок провайдеров зарезервировано (разделитель «или» + skeleton-плашка
   *   высотой одной кнопки), чтобы карточка не прыгала, когда состав придёт;
   * - `[]` — провайдеров нет: ни разделитель, ни блок не рисуются;
   * - непустой массив — рисуются кнопки в порядке массива. Утверждённая
   *   гео-модель (design-brief, блок 8): РФ — `["yandex"]`; вне РФ —
   *   `["yandex", "google", "github"]`. VK ID не существует ни в каком виде.
   *   Эталонный порядок кнопок из мокапа — Яндекс → Google → GitHub.
   */
  providers?: readonly AuthProvider[];
  onProviderSelect: (provider: AuthProvider) => void;

  /**
   * Текст ошибки для карточки блока 4 (`ErrorCard`). Пусто/`undefined` —
   * карточки нет. View не валидирует поля сам — валидацию и текст ошибки
   * готовит потребитель. Ожидаемые тексты (буквально из мокапа, секция 7,
   * скрипт `#auth-form`), чтобы feat-008 и `test-author` не выдумывали свои:
   * - пустое имя или пароль: «Введите имя и пароль.»
   * - `mode="register"`, пароль короче 8 символов: «Пароль должен содержать
   *   не менее 8 символов.»
   * - `mode="register"`, пароли не совпадают: «Пароли не совпадают.»
   */
  error?: string | null;
  /** Идёт отправка: сабмит и провайдеры заблокированы. */
  submitting?: boolean;

  className?: string;
}

const TITLES: Record<AuthMode, string> = {
  login: "Вход",
  register: "Регистрация",
};

const SUBTITLES: Record<AuthMode, string> = {
  login: "Продолжите работу со своими проектами.",
  register: "Придумайте имя и пароль — этого достаточно.",
};

const SUBMIT_LABELS: Record<AuthMode, string> = {
  login: "Войти",
  register: "Создать аккаунт",
};

// На время отправки подпись не схлопывается в «…»: многоточие — не имя, и
// кнопка переставала быть находимой и озвучиваемой («кнопка, многоточие»).
// Глагольная форма держит доступное имя и заодно сообщает состояние —
// тем же приёмом, что «Удаляем…» / «Сохранено» на экране настроек проекта.
const SUBMITTING_LABELS: Record<AuthMode, string> = {
  login: "Входим…",
  register: "Создаём аккаунт…",
};

const SWITCH_LABELS: Record<AuthMode, string> = {
  login: "Нет аккаунта? Зарегистрироваться",
  register: "Уже есть аккаунт? Войти",
};

/**
 * Полный экран входа/регистрации: `AuthLayout` (брендовый фон + сцена) +
 * карточка формы, собранная из shared `Input`/`Button` и `ErrorCard`.
 *
 * Чисто презентационный компонент (design-brief, блок 8, «Уточнение
 * архитектора»): ни запросов, ни роутинга, ни чтения гео, ни валидации —
 * всё приходит через props. `pages/login` из feat-008 собирает свою логику
 * поверх этого экрана после merge.
 *
 * Вёрстка, отступы, размеры — дословно из мокапа (`mockups/ui-polish.html`,
 * секция 7). Осознанные отступления от буквы мокапа/брифа зафиксированы в
 * `tracks/T6/summary.md`: уплотнённая геометрия `ErrorCard`, радиус карточки
 * `--radius-xl`, `autoComplete` поля пароля по режиму, а не статично.
 */
export function LoginScreenView({
  mode,
  onModeChange,
  values,
  onFieldChange,
  onSubmit,
  providers,
  onProviderSelect,
  error,
  submitting = false,
  className,
}: LoginScreenViewProps) {
  const nameId = useId();
  const passwordId = useId();
  const confirmPasswordId = useId();

  const isRegister = mode === "register";
  const passwordAutoComplete = isRegister ? "new-password" : "current-password";

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  const handleModeToggle = () => {
    onModeChange(isRegister ? "login" : "register");
  };

  return (
    <AuthLayout className={className}>
      <form
        onSubmit={handleSubmit}
        className="w-full rounded-xl border border-border bg-card p-7 text-card-foreground"
        style={{ boxShadow: "var(--shadow-input)" }}
      >
        <div className="font-serif text-[22px] font-semibold tracking-[-0.01em]">
          {TITLES[mode]}
        </div>
        <div className="mt-[3px] text-[13px] text-muted-foreground">
          {SUBTITLES[mode]}
        </div>

        <div className="mt-[18px] flex flex-col gap-2.5">
          <label htmlFor={nameId} className="sr-only">
            Имя пользователя
          </label>
          <Input
            id={nameId}
            placeholder="Имя пользователя"
            autoComplete="username"
            autoFocus
            value={values.name}
            onChange={(event) => onFieldChange("name", event.target.value)}
            disabled={submitting}
          />

          <label htmlFor={passwordId} className="sr-only">
            Пароль
          </label>
          <Input
            id={passwordId}
            type="password"
            placeholder="Пароль"
            autoComplete={passwordAutoComplete}
            value={values.password}
            onChange={(event) => onFieldChange("password", event.target.value)}
            disabled={submitting}
          />

          {isRegister && (
            <>
              <label htmlFor={confirmPasswordId} className="sr-only">
                Повторите пароль
              </label>
              <Input
                id={confirmPasswordId}
                type="password"
                placeholder="Повторите пароль"
                autoComplete="new-password"
                value={values.confirmPassword}
                onChange={(event) =>
                  onFieldChange("confirmPassword", event.target.value)
                }
                disabled={submitting}
              />
            </>
          )}

          {error && (
            <ErrorCard message={error} className="px-3.5 py-2.5 text-[13px]" />
          )}

          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={submitting}
            aria-busy={submitting || undefined}
          >
            {submitting ? SUBMITTING_LABELS[mode] : SUBMIT_LABELS[mode]}
          </Button>
        </div>

        {(providers === undefined || providers.length > 0) && (
          <>
            <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
              или
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
            </div>

            {providers === undefined ? (
              <Skeleton className="h-9 w-full rounded-lg" />
            ) : (
              <div className="flex flex-col gap-2">
                {providers.map((provider) => (
                  <ProviderButton
                    key={provider}
                    provider={provider}
                    onClick={() => onProviderSelect(provider)}
                    disabled={submitting}
                  />
                ))}
              </div>
            )}
          </>
        )}

        <Button
          type="button"
          variant="link"
          onClick={handleModeToggle}
          className="mt-3.5 w-full text-[13px]"
        >
          {SWITCH_LABELS[mode]}
        </Button>
      </form>
    </AuthLayout>
  );
}
