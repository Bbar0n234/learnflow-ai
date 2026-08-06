import { useTheme } from "@/shared/lib/use-theme";
import { getIllustration, type Scene } from "@/shared/assets/illustrations";

interface IllustrationProps {
  scene: Scene;
  alt: string;
  className?: string;
}

/**
 * Theme-aware illustration wrapper.
 * Reads the rendered theme (shared `useTheme`, без зависимости от stores) and
 * resolves the correct asset via the centralized illustrations map — switches
 * light↔dark automatically.
 */
export function Illustration({ scene, alt, className }: IllustrationProps) {
  const theme = useTheme();
  const src = getIllustration(scene, theme);
  return <img src={src} alt={alt} className={className} />;
}
