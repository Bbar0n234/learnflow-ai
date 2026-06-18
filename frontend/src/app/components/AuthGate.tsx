import { type FormEvent, type ReactNode, useState } from "react";
import { login, register } from "@/shared/api/auth";
import { getAccessToken, setAccessToken } from "@/shared/api/client";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import { logger } from "@/shared/lib/logger";
import { getApiErrorMessage } from "@/shared/lib/api-error";

type Mode = "login" | "register";

export function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState(() =>
    Boolean(getAccessToken()),
  );
  const [mode, setMode] = useState<Mode>("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");

    const trimmedName = name.trim();
    if (!trimmedName || !password) return;

    if (mode === "register") {
      if (password.length < 8) {
        setError("Пароль должен содержать не менее 8 символов");
        return;
      }
      if (password !== confirmPassword) {
        setError("Пароли не совпадают");
        return;
      }
    }

    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await login(trimmedName, password)
          : await register(trimmedName, password);
      setAccessToken(result.access_token);
      setAuthenticated(true);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err));
      logger.error("[Auth error]", err);
    } finally {
      setLoading(false);
    }
  }

  if (authenticated) return <>{children}</>;

  return (
    <Dialog open onOpenChange={() => {}} disablePointerDismissal>
      <DialogContent showCloseButton={false}>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {mode === "login" ? "Sign In" : "Create Account"}
            </DialogTitle>
            <DialogDescription>
              {mode === "login"
                ? "Enter your credentials to continue."
                : "Choose a username and password."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-4">
            <Input
              placeholder="Username"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {mode === "register" && (
              <Input
                type="password"
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            )}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          <DialogFooter className="flex flex-col gap-2 sm:flex-col">
            <Button
              type="submit"
              disabled={loading || !name.trim() || !password}
              className="w-full"
            >
              {loading
                ? "..."
                : mode === "login"
                  ? "Sign In"
                  : "Create Account"}
            </Button>
            <Button
              type="button"
              variant="link"
              className="w-full"
              onClick={() => {
                setMode(mode === "login" ? "register" : "login");
                setError("");
                setConfirmPassword("");
              }}
            >
              {mode === "login"
                ? "Don't have an account? Sign up"
                : "Already have an account? Sign in"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
