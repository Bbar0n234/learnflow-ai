import { QueryProvider } from "./QueryProvider";

export function Providers({ children }: { children: React.ReactNode }) {
  return <QueryProvider>{children}</QueryProvider>;
}
