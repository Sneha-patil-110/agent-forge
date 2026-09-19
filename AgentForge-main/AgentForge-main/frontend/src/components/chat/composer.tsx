"use client";

import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";

const MIN_ROWS = 2;
const MAX_HEIGHT_PX = 200;

export function Composer({
  disabled,
  isSending = false,
  placeholder = "Ask for a change… (e.g. \"Add authentication\")",
  onSend,
}: {
  disabled: boolean;
  isSending?: boolean;
  placeholder?: string;
  onSend: (message: string) => void;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="flex items-end gap-2 border-t border-border/60 bg-surface/40 p-3">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        disabled={disabled}
        rows={MIN_ROWS}
        aria-label="Message"
        className="min-h-16 flex-1 resize-none overflow-y-auto rounded-lg border border-border/60 bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-60"
        style={{ maxHeight: MAX_HEIGHT_PX }}
      />
      <div className="flex flex-col items-end gap-1">
        <Button
          size="icon"
          isLoading={isSending}
          disabled={disabled || value.trim() === ""}
          onClick={submit}
          aria-label="Send message"
        >
          {!isSending && <Send className="size-4" />}
        </Button>
        <span className="text-[10px] text-muted-foreground/70">{"⌘"}/Ctrl+Enter</span>
      </div>
    </div>
  );
}
