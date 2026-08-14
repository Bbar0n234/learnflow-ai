import type { ReactNode } from "react";

import { cn } from "@/shared/lib/utils";
import { Wordmark } from "@/shared/ui/Wordmark";
import { Illustration } from "@/shared/ui/Illustration";

const DEFAULT_TAGLINE =
  "Учитесь со своим ИИ-наставником: проекты, чаты и сфера знаний, которая растёт вместе с вами.";

export interface AuthLayoutProps {
  /** Слот карточки формы — правая колонка. */
  children: ReactNode;
  /** Тэглайн под wordmark. Дефолт — утверждённый мокапом текст. */
  tagline?: ReactNode;
  className?: string;
}

/**
 * Полноэкранная брендовая композиция auth-экрана: wordmark + тэглайн +
 * иллюстрация `auth-hero` в левой колонке, слот карточки формы — в правой.
 * Мокап: `.auth-frame` / `.auth-brand` / `.auth-side`
 * (`mockups/ui-polish.html`, секция 7, строки 388–392), с поправкой «рамка
 * демо → полный экран»: корень растянут на весь вьюпорт (`min-h-screen`)
 * вместо `border` + `min-height: 640px` демо-рамки.
 *
 * Ниже брейкпоинта `lg` брендовая колонка мокапом не покрыта. Решение
 * оркестратора сверх мокапа (T6/plan.md § Резолюции, п.3): колонка
 * скрывается (`hidden lg:flex`), карточка формы растягивается на всю
 * ширину, а wordmark уменьшённым переезжает шапкой над ней — карточка
 * остаётся единственным носителем функции, иллюстрация уступает место.
 *
 * Чисто презентационный компонент: ни состояния, ни эффектов, импортов выше
 * `shared/` нет.
 */
export function AuthLayout({
  children,
  tagline = DEFAULT_TAGLINE,
  className,
}: AuthLayoutProps) {
  return (
    <div className={cn("flex min-h-screen w-full bg-background", className)}>
      {/* Брендовая колонка — только от `lg` и выше (мокап её не покрывает уже) */}
      <div className="hidden flex-1 flex-col justify-center gap-[22px] p-14 lg:flex">
        <Wordmark className="text-[38px]" />
        <p className="max-w-[380px] text-[15px] leading-[1.55] text-muted-foreground">
          {tagline}
        </p>
        <Illustration
          scene="auth-hero"
          alt="Иллюстрация: Электрик приветствует"
          className="w-full max-w-[460px]"
        />
      </div>

      {/* Правая колонка — слот карточки формы; ниже `lg` несёт и уменьшённый wordmark */}
      <div className="flex w-full shrink-0 flex-col items-center justify-center gap-8 px-6 py-10 lg:w-[440px] lg:gap-0 lg:px-12 lg:py-10">
        <Wordmark className="text-[26px] lg:hidden" />
        {children}
      </div>
    </div>
  );
}
