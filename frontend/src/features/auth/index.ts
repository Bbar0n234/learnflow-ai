export { LoginScreenView } from "./ui/LoginScreenView";
export type {
  AuthMode,
  AuthFormValues,
  LoginScreenViewProps,
} from "./ui/LoginScreenView";
// Re-export, чтобы потребитель (`pages/login`, feat-008) не тянул `shared/ui`
// напрямую ради одного типа — весь контракт слайса приходит через один вход.
export type { AuthProvider } from "@/shared/ui/ProviderButton";
