import { useState, useRef, useEffect } from "react";
import {
  Bold,
  Italic,
  Strikethrough,
  Heading2,
  Heading3,
  List,
  Quote,
  Code,
  Link,
  Eye,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { cn } from "@/shared/lib/utils";
import {
  MOCK_SPHERE_HISTORY,
  type SphereVersionBump,
} from "../model/mock-sphere-version";

interface SphereEditorProps {
  content: string;
  isPending: boolean;
  error: unknown;
  onSave: (content: string) => void;
  onCancel: () => void;
}

// ─── Toolbar formatting helpers ─────────────────────────────────────────────

function applyInline(
  textarea: HTMLTextAreaElement,
  before: string,
  after: string,
  placeholder: string,
): { value: string; selectionStart: number; selectionEnd: number } {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const selected = textarea.value.substring(start, end) || placeholder;
  const newValue =
    textarea.value.substring(0, start) +
    before +
    selected +
    after +
    textarea.value.substring(end);
  return {
    value: newValue,
    selectionStart: start + before.length,
    selectionEnd: start + before.length + selected.length,
  };
}

function applyLinePrefix(
  textarea: HTMLTextAreaElement,
  prefix: string,
): { value: string; selectionStart: number; selectionEnd: number } {
  const pos = textarea.selectionStart;
  const lineStart = textarea.value.lastIndexOf("\n", pos - 1) + 1;
  const newValue =
    textarea.value.slice(0, lineStart) +
    prefix +
    textarea.value.slice(lineStart);
  return {
    value: newValue,
    selectionStart: pos + prefix.length,
    selectionEnd: pos + prefix.length,
  };
}

// ─── Version bump badge ──────────────────────────────────────────────────────

function BumpBadge({ bump }: { bump: SphereVersionBump }) {
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 font-mono text-[10px] font-medium",
        bump === "мажор"
          ? "bg-primary text-primary-foreground"
          : "bg-secondary text-secondary-foreground",
      )}
    >
      {bump}
    </span>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function SphereEditor({
  content,
  isPending,
  error,
  onSave,
  onCancel,
}: SphereEditorProps) {
  const [text, setText] = useState(content);
  const [markdownMode, setMarkdownMode] = useState(true);
  const [autosaveTime, setAutosaveTime] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Autosave: 2s after last keystroke — local state only, no API ({L0.5})
  useEffect(() => {
    if (text === content) {
      setAutosaveTime(null);
      return;
    }
    const timer = setTimeout(() => {
      const now = new Date();
      const h = now.getHours().toString().padStart(2, "0");
      const m = now.getMinutes().toString().padStart(2, "0");
      setAutosaveTime(`${h}:${m}`);
    }, 2000);
    return () => clearTimeout(timer);
  }, [text, content]);

  // ── Toolbar actions ─────────────────────────────────────────────────────

  function applyFormat(
    handler: (ta: HTMLTextAreaElement) => {
      value: string;
      selectionStart: number;
      selectionEnd: number;
    },
  ) {
    const ta = textareaRef.current;
    if (!ta) return;
    const result = handler(ta);
    setText(result.value);
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  }

  function toolbar(before: string, after = before, placeholder = "текст") {
    applyFormat((ta) => applyInline(ta, before, after, placeholder));
  }

  function toolbarPrefix(prefix: string) {
    applyFormat((ta) => applyLinePrefix(ta, prefix));
  }

  function toolbarLink() {
    applyFormat((ta) => applyInline(ta, "[", "](url)", "текст ссылки"));
  }

  function toolbarCode() {
    applyFormat((ta) => applyInline(ta, "```\n", "\n```", "код"));
  }

  function toolbarParagraph() {
    const ta = textareaRef.current;
    if (!ta) return;
    const pos = ta.selectionStart;
    const lineStart = ta.value.lastIndexOf("\n", pos - 1) + 1;
    const lineContent = ta.value.slice(lineStart);
    const stripped = lineContent.replace(/^(#{1,6}\s|[-*]\s|>\s)/, "");
    const removed = lineContent.length - stripped.length;
    const fullVal = ta.value.slice(0, lineStart) + stripped;
    setText(fullVal);
    const newPos = Math.max(lineStart, pos - removed);
    requestAnimationFrame(() => {
      ta.focus();
      ta.setSelectionRange(newPos, newPos);
    });
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Main editor area ─────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Header */}
        <div className="flex h-[56px] shrink-0 items-center justify-between border-b border-border px-6">
          <h2 className="font-serif text-lg font-semibold text-foreground">
            Редактировать сферу
          </h2>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={onCancel}
              disabled={isPending}
            >
              Отмена
            </Button>
            <Button size="sm" onClick={() => onSave(text)} disabled={isPending}>
              {isPending ? "Сохраняется…" : "Сохранить"}
            </Button>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex shrink-0 flex-wrap items-center gap-0.5 border-b border-border bg-muted/40 px-3 py-1.5">
          {/* Paragraph dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-foreground"
                />
              }
            >
              Абзац
              <ChevronDown className="h-3 w-3" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={toolbarParagraph}>
                Абзац
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => toolbarPrefix("## ")}>
                Заголовок 2
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => toolbarPrefix("### ")}>
                Заголовок 3
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* B / I / S */}
          <button
            type="button"
            title="Жирный"
            onClick={() => toolbar("**")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Bold className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Курсив"
            onClick={() => toolbar("*")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Italic className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Зачёркнутый"
            onClick={() => toolbar("~~")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Strikethrough className="h-3.5 w-3.5" />
          </button>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* H2 / H3 */}
          <button
            type="button"
            title="Заголовок 2"
            onClick={() => toolbarPrefix("## ")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Heading2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Заголовок 3"
            onClick={() => toolbarPrefix("### ")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Heading3 className="h-3.5 w-3.5" />
          </button>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* List / Quote / Code / Link */}
          <button
            type="button"
            title="Список"
            onClick={() => toolbarPrefix("- ")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Цитата"
            onClick={() => toolbarPrefix("> ")}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Quote className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Блок кода"
            onClick={toolbarCode}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Code className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            title="Ссылка"
            onClick={toolbarLink}
            className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <Link className="h-3.5 w-3.5" />
          </button>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* Markdown-режим toggle */}
          <button
            type="button"
            onClick={() => setMarkdownMode((m) => !m)}
            title={markdownMode ? "Предпросмотр" : "Markdown-режим"}
            className={cn(
              "flex h-7 items-center gap-1.5 rounded px-2 text-xs transition-colors",
              markdownMode
                ? "bg-secondary text-secondary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Eye className="h-3.5 w-3.5" />
            {markdownMode ? "Markdown" : "Предпросмотр"}
          </button>
        </div>

        {/* Error message */}
        {isSecurityViolation(error) ? (
          <p className="shrink-0 px-6 pt-3 text-sm text-destructive">
            {SECURITY_VIOLATION_MESSAGE}
          </p>
        ) : error ? (
          <p className="shrink-0 px-6 pt-3 text-sm text-destructive">
            {getApiErrorMessage(error)}
          </p>
        ) : null}

        {/* Editor body */}
        <div className="min-h-0 flex-1 overflow-hidden p-6 pb-3">
          {markdownMode ? (
            <div className="flex h-full flex-col rounded-xl border border-border bg-card shadow-none">
              <Textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                className="h-full min-h-[200px] flex-1 resize-none rounded-xl border-0 bg-transparent font-mono text-sm focus-visible:ring-0 focus-visible:ring-offset-0"
                placeholder="Напишите содержимое сферы знаний в формате Markdown…"
                disabled={isPending}
              />
            </div>
          ) : (
            <ScrollArea className="h-full rounded-xl border border-border bg-card px-6 py-4">
              {text ? (
                <div className="sphere-prose max-w-[680px]">
                  <MarkdownRenderer>{text}</MarkdownRenderer>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Начните вводить текст…
                </p>
              )}
            </ScrollArea>
          )}
        </div>

        {/* Autosave status bar */}
        <div className="flex h-8 shrink-0 items-center px-6 pb-2">
          {autosaveTime ? (
            <p className="text-xs text-muted-foreground">
              черновик сохранён · {autosaveTime}
            </p>
          ) : (
            <span className="text-xs text-muted-foreground/40">
              {text !== content ? "вводите текст…" : ""}
            </span>
          )}
        </div>
      </div>

      {/* ── Right rail: история версий ───────────────────────────────────── */}
      <div className="flex w-[252px] shrink-0 flex-col border-l border-border">
        <div className="flex h-[56px] shrink-0 items-center border-b border-border px-4">
          <h3 className="text-sm font-medium text-foreground">
            История версий
          </h3>
        </div>
        <ScrollArea className="flex-1">
          <div className="p-3">
            {MOCK_SPHERE_HISTORY.map((entry) => (
              <div
                key={entry.version}
                className="rounded-lg px-2 py-2.5 transition-colors hover:bg-muted/60"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-foreground">
                    {entry.version}
                  </span>
                  <BumpBadge bump={entry.bump} />
                </div>
                <p className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted-foreground">
                  {entry.summary}
                </p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground/60">
                  {entry.timestamp} ·{" "}
                  {entry.author === "agent" ? "агент" : "вы"}
                </p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
