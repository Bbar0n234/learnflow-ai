import { type FormEvent, type ReactNode, useState } from "react";
import { getUsername, setUsername } from "@/shared/api/client";
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

export function AuthGate({ children }: { children: ReactNode }) {
  const [name, setName] = useState(() => getUsername());
  const [input, setInput] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    setUsername(trimmed);
    setName(trimmed);
  }

  if (name) return <>{children}</>;

  return (
    <Dialog
      open
      onOpenChange={() => {
        /* prevent closing without username */
      }}
      disablePointerDismissal
    >
      <DialogContent showCloseButton={false}>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Welcome to LearnFlow</DialogTitle>
            <DialogDescription>
              Enter your name to get started.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="Your name"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!input.trim()}>
              Continue
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
