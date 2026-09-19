"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { FileText, TriangleAlert } from "lucide-react";
import { getDocumentation } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { markdownComponents } from "@/components/ui/markdown-components";

export function DocumentationTab({ runId }: { runId: string }) {
  const [activePath, setActivePath] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["documentation", runId],
    queryFn: () => getDocumentation(runId),
  });

  if (query.isLoading) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-status-failed">
        <TriangleAlert className="size-4" />
        Couldn&apos;t load documentation.
      </div>
    );
  }

  const files = query.data?.files ?? [];
  const active = files.find((file) => file.path === activePath) ?? files[0] ?? null;

  if (files.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <FileText className="size-6 opacity-50" />
        No documentation generated yet.
      </div>
    );
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[14rem_1fr] grid-rows-[minmax(0,1fr)] overflow-hidden rounded-xl border border-border/60">
      <aside className="min-h-0 overflow-y-auto border-r border-border/60 bg-surface/40 py-1">
        {files.map((file) => (
          <button
            key={file.path}
            onClick={() => setActivePath(file.path)}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
              active?.path === file.path
                ? "bg-primary/15 text-foreground"
                : "text-muted-foreground hover:bg-accent/50",
            )}
          >
            <FileText className="size-3.5 shrink-0" />
            <span className="truncate">{file.title}</span>
          </button>
        ))}
      </aside>
      <div className="min-h-0 overflow-y-auto px-8 py-6">
        {active && (
          <article className="prose prose-invert prose-sm max-w-2xl prose-pre:bg-surface-2 prose-pre:border prose-pre:border-border/60 prose-code:text-primary prose-a:text-primary">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {active.content}
            </ReactMarkdown>
          </article>
        )}
      </div>
    </div>
  );
}
