"use client";

import { useRef, useState } from "react";
import type { Components } from "react-markdown";
import { Check, Copy } from "lucide-react";

function PreWithCopyButton({ children, ...props }: React.ComponentProps<"pre">) {
  const [copied, setCopied] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  async function handleCopy() {
    const text = preRef.current?.textContent ?? "";
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="group/code relative">
      <pre ref={preRef} {...props}>
        {children}
      </pre>
      <button
        type="button"
        onClick={handleCopy}
        aria-label={copied ? "Copied" : "Copy code"}
        className="absolute top-2 right-2 rounded-md border border-border/60 bg-surface/90 p-1.5 opacity-0 transition-opacity group-hover/code:opacity-100 hover:bg-accent focus-visible:opacity-100"
      >
        {copied ? (
          <Check className="size-3.5 text-status-completed" />
        ) : (
          <Copy className="size-3.5 text-muted-foreground" />
        )}
      </button>
    </div>
  );
}

function TableWithScroll({ children, ...props }: React.ComponentProps<"table">) {
  return (
    <div className="overflow-x-auto">
      <table {...props}>{children}</table>
    </div>
  );
}

export const markdownComponents: Components = {
  pre: PreWithCopyButton,
  table: TableWithScroll,
};
