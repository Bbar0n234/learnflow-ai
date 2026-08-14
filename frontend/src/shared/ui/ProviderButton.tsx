import type { ReactElement } from "react";

import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/utils";

/**
 * Провайдеры OAuth-входа auth-экрана. Гео-состав (какие провайдеры показывать)
 * решает потребитель (`features/auth`) — этот компонент только рисует кнопку.
 * VK ID в списке нет — снят решением архитектора (design-brief, блок 8).
 */
export type AuthProvider = "yandex" | "google" | "github";

export interface ProviderButtonProps {
  provider: AuthProvider;
  /** Переопределение подписи. Дефолт — фирменная формулировка провайдера. */
  label?: string;
  onClick?: () => void;
  disabled?: boolean;
  className?: string;
}

// Между «Яндекс» и «ID» — неразрывный пробел (U+00A0), как в мокапе
// (`Войти с Яндекс&nbsp;ID`): ниже `lg` карточка тянется во всю ширину, и без
// него «ID» уезжает на вторую строку в отрыве от названия.
const DEFAULT_LABELS: Record<AuthProvider, string> = {
  yandex: "Войти с Яндекс ID",
  google: "Войти через Google",
  github: "Войти через GitHub",
};

/**
 * Кнопка входа через внешнего провайдера — брендовый знак + подпись,
 * на существующем `Button variant="outline" size="lg"`. Логика провайдера
 * (URL авторизации, редиректы) в компонент не заходит — только `onClick`.
 */
export function ProviderButton({
  provider,
  label,
  onClick,
  disabled,
  className,
}: ProviderButtonProps) {
  const Icon = PROVIDER_ICONS[provider];

  return (
    <Button
      type="button"
      variant="outline"
      size="lg"
      onClick={onClick}
      disabled={disabled}
      className={cn("w-full justify-center gap-2.5", className)}
    >
      <Icon />
      {label ?? DEFAULT_LABELS[provider]}
    </Button>
  );
}

const PROVIDER_ICONS: Record<AuthProvider, () => ReactElement> = {
  yandex: YandexIcon,
  google: GoogleIcon,
  github: GitHubIcon,
};

// ── Брендовые знаки провайдеров ──────────────────────────────────────────
// Пути — дословно из mockups/ui-polish.html (секция 7, строки 441–454).
// Цвета берутся из токенов `--provider-*` (index.css): значения фирменные и
// темизации не подлежат, но живут они всё равно переменной, а не литералом, —
// граница «нет hex/rgba в `.tsx`» абсолютна (design-system.md § Границы,
// тот же приём, что у `--slides-*` / `--scrim-overlay`).

function GoogleIcon() {
  return (
    <svg className="size-5" viewBox="0 0 48 48" aria-hidden="true">
      <path
        style={{ fill: "var(--provider-google-blue)" }}
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        style={{ fill: "var(--provider-google-green)" }}
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
      <path
        style={{ fill: "var(--provider-google-yellow)" }}
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        style={{ fill: "var(--provider-google-red)" }}
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg className="size-5" viewBox="0 0 16 16" aria-hidden="true">
      {/* Знак GitHub — единственный провайдерский цвет, который мокап меняет с
          темой (не currentColor, plan-review #3); ветвление живёт в токене. */}
      <path
        style={{ fill: "var(--provider-github-fg)" }}
        fillRule="evenodd"
        clipRule="evenodd"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
      />
    </svg>
  );
}

function YandexIcon() {
  return (
    <svg className="size-5" viewBox="0 0 24 24" aria-hidden="true">
      <circle
        cx="12"
        cy="12"
        r="11.5"
        style={{
          fill: "var(--provider-yandex-bg)",
          stroke: "var(--provider-yandex-stroke)",
        }}
      />
      <text
        x="12.6"
        y="12.6"
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily="Arial, 'Instrument Sans', sans-serif"
        fontSize="14.5"
        fontWeight="700"
        style={{ fill: "var(--provider-yandex-fg)" }}
      >
        Я
      </text>
    </svg>
  );
}
