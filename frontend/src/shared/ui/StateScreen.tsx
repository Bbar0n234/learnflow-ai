import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/shared/lib/utils";
import { Illustration } from "@/shared/ui/Illustration";
import type { Scene } from "@/shared/assets/illustrations";

/**
 * Единый брендовый шаблон «не-контента» (feat-013, блок 2 дизайн-брифа).
 *
 * Три соседних примитива, а не варианты одного пропа — у каждого своя
 * геометрия и набор слотов:
 * - `StateScreen` — полноэкранная/панельная композиция «сцена + заголовок +
 *   подпись + действие» (404, empty-state сферы/артефактов, полноэкранный error).
 * - `LoadingState` — компактный спиннер-блок без иллюстрации (панельные и
 *   Suspense-загрузки).
 * - `ErrorCard` — карточная форма ошибки списка/квери с «Повторить».
 *
 * `Skeleton` (плашка на `--muted` + `animate-pulse`) живёт отдельно —
 * `shared/ui/skeleton.tsx` (канонический shadcn-примитив). Компактные
 * состояния списков собираются потребителем из `Skeleton` + `ErrorCard`;
 * `StateScreen` в списках не обязателен — его геометрия (`text-2xl`
 * заголовок, `p-8`) не рассчитана на узкие панели.
 *
 * Рецепты для волны 2 (эталоны формы, не обязательный API — потребитель
 * собирает свою разметку по образцу). Справочно, не источник истины после
 * правок мокапа: `mockups/ui-polish.html`, секция 2а (классы `.sk-chat` /
 * `.sk-art`).
 *
 * Скелетон карточки чата (список чатов):
 * ```tsx
 * <div className="flex flex-col gap-2 rounded-[var(--radius)] p-3">
 *   <Skeleton className="h-3.5 w-[46%]" />
 *   <Skeleton className="mt-[7px] h-2.5 w-[68%]" />
 *   <div className="mt-[9px] flex items-center gap-2">
 *     <Skeleton className="h-4 w-16 rounded-full" />
 *     <Skeleton className="mt-[3px] h-2.5 w-[34px]" />
 *   </div>
 * </div>
 * ```
 *
 * Скелетон строки артефакта:
 * ```tsx
 * <div className="flex items-center gap-3 rounded-[var(--radius)] px-3 py-2.5">
 *   <Skeleton className="h-9 w-9 shrink-0 rounded-[calc(var(--radius)*0.8)]" />
 *   <div className="flex-1">
 *     <Skeleton className="h-3 w-[62%]" />
 *     <Skeleton className="mt-1.5 h-2.5 w-[32%]" />
 *   </div>
 * </div>
 * ```
 *
 * В обоих рецептах `animate-pulse` не добавляется на контейнер группы —
 * канонический shadcn-примитив `Skeleton` уже несёт его на каждой плашке
 * (`bg-muted animate-pulse rounded-md`), дублировать на группе незачем.
 */

type IllustrationSlot =
  | { scene: Scene; alt: string }
  | { scene?: never; alt?: never };

export type StateScreenProps = IllustrationSlot & {
  /** Serif-заголовок. Опционален — напр. empty-state артефактов идёт без него. */
  title?: string;
  /** Подпись. Единственный обязательный слот. */
  description: ReactNode;
  /** Слот действия — потребитель сам решает Button/Link и вариант. */
  action?: ReactNode;
  /**
   * Ширина сцены (проп на `Illustration`, не на `StateScreen`). Утверждённые
   * мокапом значения: `error-state` 280px, `artifacts-select` 300px,
   * `not-found` 360px, `empty-sphere` 440px, `auth-hero` 460px — передавать
   * как `"max-w-[280px] w-full"` и т.п.
   */
  illustrationClassName?: string;
  /**
   * Root-className, мержится через `cn()`. Базовая геометрия несёт `flex-1`
   * (полноэкранная/панельная форма из мокапа, `.state-full`) — компактные
   * панели перекрывают его классом потребителя (`flex-none` и т.п.), а не
   * форкая компонент.
   */
  className?: string;
};

/**
 * Брендовая композиция «не-контента»: иллюстрация (опционально) + заголовок
 * (опционально) + подпись + действие (опционально). Мокап: `.state-full`
 * (ui-polish.html:315-317).
 */
export function StateScreen({
  scene,
  alt,
  title,
  description,
  action,
  illustrationClassName,
  className,
}: StateScreenProps) {
  return (
    <div
      className={cn(
        "flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center",
        className,
      )}
    >
      {scene && (
        <Illustration
          scene={scene}
          alt={alt}
          className={cn("w-full", illustrationClassName)}
        />
      )}
      {title && (
        <h2 className="font-serif text-2xl font-semibold tracking-[-0.01em]">
          {title}
        </h2>
      )}
      <p className="max-w-[420px] text-sm leading-relaxed text-muted-foreground">
        {description}
      </p>
      {action}
    </div>
  );
}

export interface LoadingStateProps {
  /** Подпись рядом со спиннером. Дефолт — типографское «Загрузка…». */
  label?: string;
  /** Растяжка по месту (`flex-1`, `h-full` и т.п.) — по умолчанию не задана. */
  className?: string;
}

/**
 * Компактная панельная/Suspense-загрузка: `Loader2` в `animate-spin` +
 * подпись, без иллюстрации (загрузка — переходное состояние). Мокап:
 * `.state-inline` (ui-polish.html:311).
 */
export function LoadingState({
  label = "Загрузка…",
  className,
}: LoadingStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 text-muted-foreground",
        className,
      )}
    >
      <Loader2 className="size-5 animate-spin" aria-hidden="true" />
      <span className="text-sm">{label}</span>
    </div>
  );
}

export interface ErrorCardProps {
  /** Текст ошибки. */
  message: ReactNode;
  /** Обработчик «Повторить». Без него кнопка не рисуется — просто карточка. */
  onRetry?: () => void;
  /** Текст кнопки. Дефолт — «Повторить». */
  retryLabel?: string;
  className?: string;
}

/**
 * Канонная карточная форма ошибки (списки, per-query): сообщение слева,
 * действие «Повторить» справа. Мокап: `.err-card` (ui-polish.html:312-314).
 */
export function ErrorCard({
  message,
  onRetry,
  retryLabel = "Повторить",
  className,
}: ErrorCardProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive",
        className,
      )}
    >
      <span>{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="shrink-0 font-medium text-destructive underline underline-offset-[3px] transition-opacity hover:opacity-80"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
