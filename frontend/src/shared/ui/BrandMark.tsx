import { cn } from "@/shared/lib/utils";
import { SphereOrb } from "./SphereOrb";

/**
 * BrandMark — знак для аватара агента и мелких контекстов.
 * Орб в тонком кольце (1.5px, --brand-lavender). Без спарков — кольцо само
 * выступает декоративным обрамлением.
 */
interface BrandMarkProps {
  /** Внешний диаметр (включая кольцо). По умолчанию 36px. */
  size?: number;
  className?: string;
}

export function BrandMark({ size = 36, className }: BrandMarkProps) {
  const orbSize = size - 6; // 3px кольца с каждой стороны

  return (
    <div
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center rounded-full",
        className,
      )}
      style={{
        width: size,
        height: size,
        border: "1.5px solid var(--brand-lavender)",
      }}
    >
      <SphereOrb size={orbSize} showRings={false} showSparks={false} />
    </div>
  );
}
