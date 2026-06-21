import { cn } from "@/shared/lib/utils";

/**
 * SphereOrb — брендовая Сфера знаний.
 *
 * Единственное место с радиальным градиентом в дизайн-системе (правило «фиолетовый плоский,
 * градиент только в орбе»). Токены --orb-gradient / --orb-shadow / --orb-ring-* определены
 * в index.css (light + dark) и переключаются автоматически по классу .dark на <html>.
 *
 * Размеры: 148 (панель сферы) / 44 (знак/BrandMark) / 20 (мини, проектные карточки) / 16 (чистый).
 * При size >= 100 добавляются 2 концентрических кольца; при size >= 30 — искры-ромбы.
 */
interface SphereOrbProps {
  size?: number;
  showRings?: boolean;
  showSparks?: boolean;
  className?: string;
}

export function SphereOrb({
  size = 148,
  showRings,
  showSparks,
  className,
}: SphereOrbProps) {
  const rings = showRings ?? size >= 100;
  const sparks = showSparks ?? size >= 30;

  const ring1 = size + 20;
  const ring2 = size + 40;
  // container accommodates rings; otherwise equals orb size (overflow: visible for sparks)
  const containerSize = rings ? size + 48 : size;

  // Compute spark positions at the orb surface for a given angle from top (clockwise)
  function sparkAt(angleDeg: number, sparkSize: number) {
    const a = (angleDeg * Math.PI) / 180;
    const cx = containerSize / 2;
    const cy = containerSize / 2;
    const r = size / 2;
    return {
      top: Math.round(cy - r * Math.cos(a) - sparkSize / 2),
      left: Math.round(cx + r * Math.sin(a) - sparkSize / 2),
    };
  }

  const sp1 = Math.max(6, Math.round(size * 0.068));
  const sp2 = Math.max(4, Math.round(size * 0.043));
  const sp3 = Math.max(3, Math.round(size * 0.035));

  const pos1 = sparkAt(40, sp1); // top-right area, brand-lavender
  const pos2 = sparkAt(62, sp2); // further right, primary accent
  const pos3 = sparkAt(16, sp3); // slightly right of top, near-white

  return (
    <div
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center",
        className,
      )}
      style={{ width: containerSize, height: containerSize }}
    >
      {/* Outer concentric ring */}
      {rings && (
        <div
          className="absolute rounded-full"
          style={{
            width: ring2,
            height: ring2,
            border: "1px solid var(--orb-ring-2)",
          }}
        />
      )}
      {/* Inner concentric ring */}
      {rings && (
        <div
          className="absolute rounded-full"
          style={{
            width: ring1,
            height: ring1,
            border: "1px solid var(--orb-ring-1)",
          }}
        />
      )}
      {/* The orb */}
      <div
        className="absolute rounded-full"
        style={{
          width: size,
          height: size,
          background: "var(--orb-gradient)",
          boxShadow: "var(--orb-shadow)",
        }}
      />
      {/* Diamond sparks */}
      {sparks && (
        <>
          {/* Spark 1: brand-lavender, ~40° from top */}
          <div
            className="absolute"
            style={{
              width: sp1,
              height: sp1,
              background: "var(--brand-lavender)",
              transform: "rotate(45deg)",
              top: pos1.top,
              left: pos1.left,
            }}
          />
          {/* Spark 2: primary accent, ~62° from top */}
          {size >= 30 && (
            <div
              className="absolute"
              style={{
                width: sp2,
                height: sp2,
                background: "var(--primary)",
                transform: "rotate(45deg)",
                top: pos2.top,
                left: pos2.left,
              }}
            />
          )}
          {/* Spark 3: near-white/cream highlight, ~16° from top */}
          {size >= 80 && (
            <div
              className="absolute"
              style={{
                width: sp3,
                height: sp3,
                background: "var(--primary-foreground)",
                transform: "rotate(45deg)",
                top: pos3.top,
                left: pos3.left,
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
