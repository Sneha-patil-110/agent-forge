"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { FileSearch, FileText, Hash, TextSearch } from "lucide-react";
import { getFileContent } from "@/lib/api";
import { getFileIcon, isMarkdown } from "@/lib/file-icons";
import { cn } from "@/lib/utils";
import type { FileTreeNode } from "@/lib/types";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

interface ContentMatch {
  path: string;
  line: number;
  snippet: string;
}

type Mode = "files" | "content" | "current" | "markdown";

const MODES: { value: Mode; label: string; icon: React.ElementType }[] = [
  { value: "files", label: "Files", icon: FileSearch },
  { value: "content", label: "Repository", icon: Hash },
  { value: "current", label: "Current file", icon: TextSearch },
  { value: "markdown", label: "Markdown", icon: FileText },
];

export function QuickOpen({
  runId,
  open,
  onOpenChange,
  files,
  activePath,
  activeContent,
  onSelect,
}: {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  files: FileTreeNode[];
  activePath?: string | null;
  activeContent?: string;
  onSelect: (path: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode>("files");

  useEffect(() => {
    if (!open) {
      setQuery("");
      setMode("files");
    }
  }, [open]);

  const markdownFiles = useMemo(() => files.filter((file) => isMarkdown(file.path)), [files]);
  const searchScope = mode === "markdown" ? markdownFiles : files;
  const isRepoSearch = mode === "content" || mode === "markdown";

  const contentQueries = useQueries({
    queries: searchScope.map((file) => ({
      queryKey: ["file-content", runId, file.path],
      queryFn: () => getFileContent(runId, file.path),
      enabled: isRepoSearch && query.trim().length > 1,
      staleTime: Infinity,
    })),
  });

  const contentMatches = useMemo<ContentMatch[]>(() => {
    if (!isRepoSearch || query.trim().length < 2) return [];

    const needle = query.trim().toLowerCase();
    const matches: ContentMatch[] = [];

    contentQueries.forEach((result, index) => {
      const file = searchScope[index];
      const content = result.data?.content;
      if (!content) return;

      const lines = content.split("\n");
      for (let i = 0; i < lines.length; i += 1) {
        if (lines[i].toLowerCase().includes(needle)) {
          matches.push({ path: file.path, line: i + 1, snippet: lines[i].trim().slice(0, 120) });
          if (matches.filter((m) => m.path === file.path).length >= 3) break;
        }
      }
    });

    return matches.slice(0, 50);
  }, [isRepoSearch, query, contentQueries, searchScope]);

  const currentFileMatches = useMemo<ContentMatch[]>(() => {
    if (mode !== "current" || !activePath || !activeContent || query.trim().length < 2) return [];

    const needle = query.trim().toLowerCase();
    const matches: ContentMatch[] = [];
    const lines = activeContent.split("\n");

    for (let i = 0; i < lines.length; i += 1) {
      if (lines[i].toLowerCase().includes(needle)) {
        matches.push({ path: activePath, line: i + 1, snippet: lines[i].trim().slice(0, 160) });
      }
      if (matches.length >= 50) break;
    }

    return matches;
  }, [mode, activePath, activeContent, query]);

  const isLoadingContent = isRepoSearch && query.trim().length > 1 && contentQueries.some((q) => q.isFetching);

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Quick open"
      description="Search files by name or content"
    >
      <CommandInput placeholder="Search…" value={query} onValueChange={setQuery} />
      <div className="flex items-center gap-1 border-b border-border/60 px-2 py-1.5">
        {MODES.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            onClick={() => setMode(value)}
            disabled={value === "current" && !activePath}
            className={cn(
              "flex items-center gap-1 rounded-md px-2 py-1 text-xs disabled:opacity-40",
              mode === value ? "bg-accent text-foreground" : "text-muted-foreground",
            )}
          >
            <Icon className="size-3" />
            {label}
            {value === "content" && isLoadingContent && mode === "content" && " (searching…)"}
          </button>
        ))}
      </div>
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>
        {mode === "files" ? (
          <CommandGroup heading="Files">
            {files.map((file) => {
              const { icon: Icon, color } = getFileIcon(file.name);
              return (
                <CommandItem
                  key={file.path}
                  value={file.path}
                  onSelect={() => {
                    onSelect(file.path);
                    onOpenChange(false);
                  }}
                >
                  <Icon className={cn("size-3.5", color)} />
                  <span className="truncate">{file.name}</span>
                  <span className="ml-2 truncate text-xs text-muted-foreground">{file.path}</span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        ) : mode === "current" ? (
          <CommandGroup heading={activePath ? `Matches in ${activePath} (${currentFileMatches.length})` : "No file open"}>
            {currentFileMatches.map((match) => (
              <CommandItem
                key={match.line}
                value={`current:${match.line}`}
                onSelect={() => onOpenChange(false)}
              >
                <TextSearch className="size-3.5 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">L{match.line}</span>
                <span className="ml-2 truncate font-mono text-xs">{match.snippet}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : (
          <CommandGroup heading={`${mode === "markdown" ? "Markdown" : "Content"} matches (${contentMatches.length})`}>
            {contentMatches.map((match) => (
              <CommandItem
                key={`${match.path}:${match.line}`}
                value={`${match.path}:${match.line}`}
                onSelect={() => {
                  onSelect(match.path);
                  onOpenChange(false);
                }}
              >
                <Hash className="size-3.5 text-muted-foreground" />
                <span className="truncate font-mono text-xs">{match.path}</span>
                <span className="ml-2 truncate text-xs text-muted-foreground">
                  L{match.line}: {match.snippet}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandSeparator />
      </CommandList>
    </CommandDialog>
  );
}
