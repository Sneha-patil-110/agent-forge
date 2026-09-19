"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, RotateCcw, XCircle } from "lucide-react";
import { getRunTimeline } from "@/lib/api";
import type { MCPCallOut, TimelineEntryOut } from "@/lib/types";
import { cn } from "@/lib/utils";

function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function mcpCallsForEntry(entry: TimelineEntryOut, allEntries: TimelineEntryOut[], calls: MCPCallOut[]): MCPCallOut[] {
  const sameAgentEntries = allEntries.filter((candidate) => candidate.agent === entry.agent);
  const isLastAttemptForAgent = entry === sameAgentEntries[sameAgentEntries.length - 1];

  return calls.filter((call) => {
    if (call.agent !== entry.agent) return false;

    if (entry.started_at && entry.completed_at) {
      const occurred = new Date(call.occurred_at).getTime();
      return occurred >= new Date(entry.started_at).getTime() && occurred <= new Date(entry.completed_at).getTime();
    }

    return isLastAttemptForAgent;
  });
}

export function WorkflowTimeline({ runId }: { runId: string }) {
  const { data } = useQuery({
    queryKey: ["run-timeline", runId],
    queryFn: () => getRunTimeline(runId),
  });

  const entries = data?.entries ?? [];
  const mcpCalls = data?.mcp_calls ?? [];

  if (entries.length === 0) return null;

  return (
    <div className="surface-card rounded-xl border border-border/60 p-4">
      <p className="mb-3 text-xs font-medium text-muted-foreground">Workflow timeline</p>
      <ol className="space-y-1.5">
        {entries.map((entry, index) => {
          const isRetry = entry.attempt_number > 1;
          const isFailure = entry.status === "failure";
          const entryMcpCalls = mcpCallsForEntry(entry, entries, mcpCalls);

          return (
            <li key={index} className="rounded-lg px-2 py-1">
              <div className="flex items-center gap-2.5 text-sm">
                {isFailure ? (
                  <XCircle className="size-3.5 shrink-0 text-status-failed" />
                ) : (
                  <CheckCircle2 className="size-3.5 shrink-0 text-status-completed" />
                )}
                <span className="capitalize text-foreground/90">{entry.agent.replace("_", " ")}</span>
                {isRetry && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                      isFailure
                        ? "border-status-failed/30 text-status-failed"
                        : "border-status-completed/30 text-status-completed",
                    )}
                  >
                    <RotateCcw className="size-2.5" />
                    attempt {entry.attempt_number}
                  </span>
                )}
                {entry.recovery_reason && (
                  <span className="text-xs text-muted-foreground">{entry.recovery_reason.replace(/_/g, " ")}</span>
                )}
                <span className="ml-auto shrink-0 font-mono text-xs text-muted-foreground">
                  {formatDuration(entry.duration_ms)}
                </span>
              </div>

              {entryMcpCalls.length > 0 && (
                <ul className="mt-1 ml-6 space-y-0.5 border-l border-border/60 pl-3">
                  {entryMcpCalls.map((call, callIndex) => (
                    <li
                      key={callIndex}
                      className="flex items-center gap-1.5 py-0.5 text-xs text-muted-foreground"
                    >
                      {call.success ? (
                        <CheckCircle2 className="size-2.5 shrink-0 text-status-completed" />
                      ) : (
                        <XCircle className="size-2.5 shrink-0 text-status-failed" />
                      )}
                      <span className="font-mono">
                        {call.server_name}.{call.tool_name}
                      </span>
                      <span className="ml-auto shrink-0 font-mono">{formatDuration(call.duration_ms)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
