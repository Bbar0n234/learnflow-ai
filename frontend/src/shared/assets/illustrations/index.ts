// Centralized illustration map — единственная точка свапа (feat-006).
// Компоненты обращаются к ассетам только через getIllustration(), без прямых импортов PNG.

import welcomeHeroLight from "./light/welcome-hero.png";
import sidebarVignetteLight from "./light/sidebar-vignette.png";
import emptyChatsLight from "./light/empty-chats.png";
import emptySphereLight from "./light/empty-sphere.png";
import emptyArtifactsLight from "./light/empty-artifacts.png";
import errorStateLight from "./light/error-state.png";
import notFoundLight from "./light/not-found.png";
import artifactsSelectLight from "./light/artifacts-select.png";
import authHeroLight from "./light/auth-hero.png";

import welcomeHeroDark from "./dark/welcome-hero.png";
import sidebarVignetteDark from "./dark/sidebar-vignette.png";
import emptyChatsDark from "./dark/empty-chats.png";
import emptySphereDark from "./dark/empty-sphere.png";
import emptyArtifactsDark from "./dark/empty-artifacts.png";
import errorStateDark from "./dark/error-state.png";
import notFoundDark from "./dark/not-found.png";
import artifactsSelectDark from "./dark/artifacts-select.png";
import authHeroDark from "./dark/auth-hero.png";

export type Scene =
  | "welcome-hero"
  | "sidebar-vignette"
  | "empty-chats"
  | "empty-sphere"
  | "empty-artifacts"
  | "error-state"
  | "not-found"
  | "artifacts-select"
  | "auth-hero";

export type IllustrationTheme = "light" | "dark";

const illustrations: Record<IllustrationTheme, Record<Scene, string>> = {
  light: {
    "welcome-hero": welcomeHeroLight,
    "sidebar-vignette": sidebarVignetteLight,
    "empty-chats": emptyChatsLight,
    "empty-sphere": emptySphereLight,
    "empty-artifacts": emptyArtifactsLight,
    "error-state": errorStateLight,
    "not-found": notFoundLight,
    "artifacts-select": artifactsSelectLight,
    "auth-hero": authHeroLight,
  },
  dark: {
    "welcome-hero": welcomeHeroDark,
    "sidebar-vignette": sidebarVignetteDark,
    "empty-chats": emptyChatsDark,
    "empty-sphere": emptySphereDark,
    "empty-artifacts": emptyArtifactsDark,
    "error-state": errorStateDark,
    "not-found": notFoundDark,
    "artifacts-select": artifactsSelectDark,
    "auth-hero": authHeroDark,
  },
};

/**
 * Returns the resolved asset URL for a given scene and theme.
 * This is the only place where illustration assets are imported.
 */
export function getIllustration(
  scene: Scene,
  theme: IllustrationTheme,
): string {
  return illustrations[theme][scene];
}
