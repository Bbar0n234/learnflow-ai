import { cn } from "@/shared/lib/utils";

/**
 * Wordmark K5 — финальный логотип LearnFlowAI.
 *
 * Полная форма (по умолчанию): LearnFlowAI
 *   - «o» во Flow = Сфера-орб (радиальный градиент, орбитальное кольцо -18°, искра-ромб)
 *   - «AI» цветом var(--ring) (= --primary в light, #B194FF в dark), обведено рукописным кружком
 *     из двух эллипсов-бордеров
 *
 * Короткая форма (short=true): LearnFlow
 *   - Та же сфера на «o», без кружка и цветного «AI»
 *
 * Шрифт: Instrument Sans 700, tracking -0.015em (letter-spacing).
 * Размер: наследуется от родителя (em-единицы внутри).
 * Цвет основного текста: наследуется от родителя (currentColor).
 * Темо-зависимость: через CSS-переменные (--orb-gradient, --ring, --brand-lavender),
 * переключаемые классом .dark на <html>.
 */
interface WordmarkProps {
  /** true = короткая форма «LearnFlow» (sidebar, шапки). По умолчанию false = «LearnFlowAI». */
  short?: boolean;
  className?: string;
}

export function Wordmark({ short = false, className }: WordmarkProps) {
  return (
    <span
      className={cn("inline-flex items-center font-sans font-bold", className)}
      style={{ letterSpacing: "-0.015em" }}
    >
      {/* «LearnFl» */}
      <span>LearnFl</span>

      {/* «o» → Сфера-орб inline */}
      <OrbLetter />

      {/* «w» */}
      <span>w</span>

      {/* «AI» с рукописным кружком — только в полной форме */}
      {!short && <AiWithCircle />}
    </span>
  );
}

/**
 * Встроенный орб-«o»: круг с градиентом + наклонное орбитальное кольцо + искра-ромб.
 * Все размеры — в em, чтобы масштабироваться вместе с родительским font-size.
 */
function OrbLetter() {
  // Диаметр орба ≈ 0.8em (по спеке wordmark K5), сдвиг вниз ~1px к базовой линии
  const orbD = "0.8em";
  // Орбитальное кольцо: шире сферы на 5px с каждой стороны; высота ~0.7× ширины (перспектива)
  const ringW = "calc(0.8em + 10px)";
  const ringH = "calc(0.56em + 7px)"; // 0.7 × (0.8em + 10px)

  return (
    <span
      className="relative inline-flex items-center justify-center"
      style={{
        width: orbD,
        height: orbD,
        // Небольшой сдвиг вниз для посадки на базовую линию
        verticalAlign: "middle",
        transform: "translateY(0.05em)",
        // overflow visible — искра и кольцо слегка выходят за контейнер
        overflow: "visible",
      }}
    >
      {/* Орб-круг с радиальным градиентом */}
      <span
        aria-hidden="true"
        className="absolute inset-0 rounded-full"
        style={{
          background: "var(--orb-gradient)",
        }}
      />
      {/* Орбитальное кольцо (эллипс, -18°, акцент 65%) */}
      <span
        aria-hidden="true"
        className="absolute"
        style={{
          width: ringW,
          height: ringH,
          border: "1.5px solid",
          borderColor: "color-mix(in srgb, var(--ring) 65%, transparent)",
          borderRadius: "50%",
          transform: "rotate(-18deg)",
        }}
      />
      {/* Искра-ромб (~0.2em, brand-lavender, у правого верхнего края) */}
      <span
        aria-hidden="true"
        className="absolute"
        style={{
          width: "0.2em",
          height: "0.2em",
          background: "var(--brand-lavender)",
          transform: "rotate(45deg)",
          // Позиция: правый верхний угол, чуть за границей орба
          top: "-0.12em",
          right: "-0.08em",
        }}
      />
    </span>
  );
}

/**
 * «AI» с рукописным кружком (два эллипса-бордера поверх текста).
 * Цвет: var(--ring) — #7434F4 в light, #B194FF в dark.
 */
function AiWithCircle() {
  return (
    <span className="relative inline-block" style={{ color: "var(--ring)" }}>
      AI
      {/* Эллипс 1: rotate -9°, акцент 75%, inset -2px -4px */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute"
        style={{
          inset: "-2px -4px",
          border: "1.5px solid",
          borderColor: "color-mix(in srgb, var(--ring) 75%, transparent)",
          borderRadius: "50%",
          transform: "rotate(-9deg)",
        }}
      />
      {/* Эллипс 2: rotate +8°, акцент 35%, inset -4px -6px */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute"
        style={{
          inset: "-4px -6px",
          border: "1.5px solid",
          borderColor: "color-mix(in srgb, var(--ring) 35%, transparent)",
          borderRadius: "50%",
          transform: "rotate(8deg)",
        }}
      />
    </span>
  );
}
