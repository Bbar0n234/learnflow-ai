import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { Wordmark } from "@/shared/ui/Wordmark";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";

export type LoginMode = "login" | "register";

/**
 * Каркас `/login` по структуре мокапа feat-013 (секция 7, `.auth-frame`):
 * брендовая половина (wordmark + tagline) + карточка формы. Чисто
 * презентационный компонент — вся auth-логика приходит пропсами из
 * `LoginPage`. Форма пропсов держится близко к будущему презентационному
 * `features/auth/ui/LoginScreenView` (feat-013), чтобы подмена после merge
 * была заменой импорта, а не переписыванием контейнера.
 */
export interface LoginScreenViewProps {
  mode: LoginMode;
  name: string;
  password: string;
  confirmPassword: string;
  onNameChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onPasswordChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onConfirmPasswordChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onModeToggle: () => void;
  error: string;
  loading: boolean;
  /** Блок кнопок провайдеров — слот каркаса, пуст при пустом составе провайдеров. */
  providersSlot?: ReactNode;
}

const TITLE: Record<LoginMode, string> = {
  login: "Вход",
  register: "Регистрация",
};

const SUBTITLE: Record<LoginMode, string> = {
  login: "Продолжите работу со своими проектами.",
  register: "Создайте аккаунт, чтобы начать работу.",
};

const SUBMIT_LABEL: Record<LoginMode, string> = {
  login: "Войти",
  register: "Зарегистрироваться",
};

const SWITCH_LABEL: Record<LoginMode, string> = {
  login: "Нет аккаунта? Зарегистрироваться",
  register: "Уже есть аккаунт? Войти",
};

export function LoginScreenView({
  mode,
  name,
  password,
  confirmPassword,
  onNameChange,
  onPasswordChange,
  onConfirmPasswordChange,
  onSubmit,
  onModeToggle,
  error,
  loading,
  providersSlot,
}: LoginScreenViewProps) {
  return (
    <div className="flex min-h-full items-center justify-center px-8 py-12">
      <div className="flex w-full max-w-4xl overflow-hidden rounded-xl border border-border">
        {/* auth-brand: wordmark + tagline (иллюстрация — актив feat-013, в каркас не входит) */}
        <div className="hidden flex-1 flex-col justify-center gap-5 p-14 md:flex">
          <h1 className="text-4xl">
            <Wordmark />
          </h1>
          <p className="max-w-sm text-[15px] leading-relaxed text-muted-foreground">
            Учитесь со своим ИИ-наставником: проекты, чаты и сфера знаний,
            которая растёт вместе с вами.
          </p>
        </div>

        {/* auth-side: карточка формы */}
        <div className="flex w-full items-center justify-center p-10 md:w-[440px] md:shrink-0">
          <form
            onSubmit={onSubmit}
            noValidate
            className="w-full rounded-xl border border-border bg-card p-7 text-card-foreground"
            style={{ boxShadow: "var(--shadow-input)" }}
          >
            <h2 className="font-serif text-[22px] font-semibold tracking-tight">
              {TITLE[mode]}
            </h2>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {SUBTITLE[mode]}
            </p>

            <div className="mt-4 flex flex-col gap-2.5">
              {/* Видимых подписей у полей в мокапе нет — accessible name даёт
                  `aria-label`, дублируя текст placeholder'а. */}
              <Input
                aria-label="Имя пользователя"
                placeholder="Имя пользователя"
                autoComplete="username"
                value={name}
                onChange={onNameChange}
                autoFocus
              />
              <Input
                type="password"
                aria-label="Пароль"
                placeholder="Пароль"
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                value={password}
                onChange={onPasswordChange}
              />
              {mode === "register" && (
                <Input
                  type="password"
                  aria-label="Повторите пароль"
                  placeholder="Повторите пароль"
                  autoComplete="new-password"
                  value={confirmPassword}
                  onChange={onConfirmPasswordChange}
                />
              )}
              {error && (
                <p
                  role="alert"
                  className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-[13px] text-destructive"
                >
                  {error}
                </p>
              )}
              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={loading || !name.trim() || !password}
              >
                {loading ? "…" : SUBMIT_LABEL[mode]}
              </Button>
            </div>

            {providersSlot && (
              <>
                <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                  или
                  <span aria-hidden="true" className="h-px flex-1 bg-border" />
                </div>
                {providersSlot}
              </>
            )}

            <div className="text-center">
              {/* Подпись тумблера — самая длинная строка карточки, а базовый
                  `Button` держит `whitespace-nowrap` + фиксированную высоту
                  размера: на узких вьюпортах кнопка не отдавала ширину и
                  вылезала за карточку. Перекрываем на месте использования —
                  общий примитив трогать незачем. */}
              <Button
                type="button"
                variant="link"
                onClick={onModeToggle}
                className="h-auto min-h-8 max-w-full whitespace-normal"
              >
                {SWITCH_LABEL[mode]}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
