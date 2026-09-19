"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, Loader2, Play, Search, TriangleAlert, Wrench } from "lucide-react";
import { executeMCPTool, listMCPTools } from "@/lib/api";
import type { MCPToolOut } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { SchemaForm } from "@/components/mcp/schema-form";
import { cn } from "@/lib/utils";

function ToolRow({ tool }: { tool: MCPToolOut }) {
  const [expanded, setExpanded] = useState(false);
  const [args, setArgs] = useState<Record<string, unknown>>({});

  const run = useMutation({
    mutationFn: () => executeMCPTool({ tool_identity: tool.identity, arguments: args }),
  });

  return (
    <div className="rounded-lg border border-border/60 bg-surface-2/40">
      <button
        onClick={() => setExpanded((current) => !current)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-xs text-foreground">{tool.identity}</p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">{tool.description || "No description."}</p>
        </div>
        <ChevronDown
          className={cn("size-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")}
        />
      </button>
      {expanded && (
        <div className="space-y-3 border-t border-border/60 px-3 py-2.5">
          <SchemaForm schema={tool.input_schema} values={args} onChange={setArgs} />

          <Button
            size="xs"
            variant="outline"
            disabled={run.isPending}
            onClick={() => run.mutate()}
            className="gap-1.5"
          >
            {run.isPending ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
            Try it
          </Button>

          {run.isError && (
            <div className="flex items-start gap-2 rounded-md border border-status-failed/30 bg-status-failed/5 px-2.5 py-2 text-xs text-status-failed">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              {run.error instanceof Error ? run.error.message : "Request failed."}
            </div>
          )}

          {run.isSuccess && (
            <div
              className={cn(
                "rounded-md border px-2.5 py-2 text-xs",
                run.data.success
                  ? "border-border/60 bg-surface-2/60 text-foreground"
                  : "border-status-failed/30 bg-status-failed/5 text-status-failed"
              )}
            >
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap font-mono">
                {run.data.error ?? run.data.data ?? "(empty result)"}
              </pre>
              {run.data.truncated && <p className="mt-1 text-muted-foreground">(truncated)</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function McpToolExplorer() {
  const [query, setQuery] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["mcp-tools"],
    queryFn: () => listMCPTools(),
  });

  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const tools = (data?.tools ?? []).filter(
      (tool) =>
        !needle ||
        tool.tool_name.toLowerCase().includes(needle) ||
        tool.description.toLowerCase().includes(needle),
    );

    const bySer: Record<string, MCPToolOut[]> = {};
    for (const tool of tools) {
      (bySer[tool.server_name] ??= []).push(tool);
    }
    return bySer;
  }, [data, query]);

  const serverNames = Object.keys(grouped).sort();

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search tools by name or description…"
          className="pl-8"
        />
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      ) : serverNames.length === 0 ? (
        <div className="surface-card flex flex-col items-center gap-2 rounded-xl px-4 py-10 text-center text-muted-foreground">
          <Wrench className="size-5" />
          <p className="text-sm">
            {query ? "No tools match your search." : "No tools discovered yet. Refresh the registry above."}
          </p>
        </div>
      ) : (
        serverNames.map((serverName) => (
          <div key={serverName} className="space-y-1.5">
            <h4 className="px-1 text-xs font-medium text-muted-foreground">{serverName}</h4>
            <div className="space-y-1.5">
              {grouped[serverName].map((tool) => (
                <ToolRow key={tool.identity} tool={tool} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
