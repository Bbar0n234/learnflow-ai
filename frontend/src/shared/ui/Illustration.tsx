import { useThemeStore } from "@/stores/theme-store";
import { getIllustration, type Scene } from "@/shared/assets/illustrations";

interface IllustrationProps {
  scene: Scene;
  alt: string;
  className?: string;
}

/**
 * Theme-aware illustration wrapper.
 * Reads current theme from theme-store (T1) and resolves the correct asset
 * via the centralized illustrations map — switches light↔dark automatically.
 */
export function Illustration({ scene, alt, className }: IllustrationProps) {
  const theme = useThemeStore((s) => s.theme);
  const src = getIllustration(scene, theme);
  return <img src={src} alt={alt} className={className} />;
}
