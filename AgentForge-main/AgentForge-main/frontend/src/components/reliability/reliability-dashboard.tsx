"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronDown, ChevronRight, TriangleAlert } from "lucide-react";
import { getAgentReliabilityDetail, getReliabilitySummary } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";
import type { AgentStatsOut } from "@/lib/types";

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="surface-card rounded-xl border border-border/60 p-4">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

function BreakdownList({ breakdown }: { breakdown: Record<string, number> }) {
  const entries = Object.entries(breakdown).sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">No data yet.</p>;
  }

  return (
    <ul className="space-y-1">
      {entries.map(([key, count]) => (
        <li key={key} className="flex items-center justify-between text-xs">
          <span className="capitalize text-foreground/80">{key.replace(/_/g, " ")}</span>
          <span className="font-mono text-muted-foreground">{count}</span>
        </li>
      ))}
    </ul>
  );
}

function AgentRow({ stats }: { stats: AgentStatsOut }) {
  const [expanded, setExpanded] = useState(false);

  const detailQuery = useQuery({
    queryKey: ["reliability-agent", stats.agent],
    queryFn: () => getAgentReliabilityDetail(stats.agent),
    enabled: expanded,
  });

  const isRisky = stats.success_rate < 0.7 && stats.total >= 3;

  return (
    <>
      <tr
        className="cursor-pointer border-b border-border/40 text-sm hover:bg-accent/40"
        onClick={() => setExpanded((value) => !value)}
      >
        <td className="flex items-center gap-1.5 py-2 pl-1 capitalize text-foreground/90">
          {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          {stats.agent.replace("_", " ")}
        </td>
        <td className="py-2 text-right font-mono">{stats.total}</td>
        <td className="py-2 text-right">
          <span
            className={cn(
              "font-mono",
              isRisky ? "text-status-failed" : "text-status-completed",
            )}
          >
            {formatPercent(stats.success_rate)}
          </span>
        </td>
        <td className="py-2 text-right font-mono text-muted-foreground">
          {formatDuration(stats.avg_duration_ms)}
        </td>
        <td className="py-2 pr-1 text-right font-mono text-muted-foreground">
          {stats.avg_input_tokens ? Math.round(stats.avg_input_tokens) : "—"}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border/40 bg-surface-2/50">
          <td colSpan={5} className="px-4 py-3">
            {detailQuery.isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted-foreground">Failure reasons</p>
                  <BreakdownList breakdown={detailQuery.data?.recovery_reason_breakdown ?? {}} />
                </div>
                <div>
                  <p className="mb-1.5 text-xs font-medium text-muted-foreground">Recent failures</p>
                  {detailQuery.data?.recent_failures.length ? (
                    <ul className="space-y-1.5">
                      {detailQuery.data.recent_failures.slice(0, 5).map((failure, index) => (
                        <li key={index} className="text-xs">
                          <span className="font-mono text-muted-foreground">{failure.run_id}</span>
                          {failure.error_message && (
                            <p className="truncate text-foreground/80">{failure.error_message}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-muted-foreground">No recorded failures.</p>
                  )}
                </div>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export function ReliabilityDashboard() {
  const summaryQuery = useQuery({
    queryKey: ["reliability-summary"],
    queryFn: () => getReliabilitySummary(),
  });

  const sortedAgents = useMemo(() => {
    const agents = summaryQuery.data?.per_agent ?? [];
    return [...agents].sort((a, b) => a.success_rate - b.success_rate);
  }, [summaryQuery.data]);

  if (summaryQuery.isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[0, 1, 2].map((index) => (
            <Skeleton key={index} className="h-24 w-full rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (summaryQuery.isError || !summaryQuery.data) {
    return (
      <div className="surface-card flex items-start gap-3 rounded-xl px-4 py-4 text-sm text-muted-foreground">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-status-failed" />
        Couldn&apos;t load reliability data.
      </div>
    );
  }

  const summary = summaryQuery.data;

  if (summary.overall_total === 0) {
    return (
      <EmptyState
        icon={Activity}
        title="No agent invocations recorded yet"
        description="This dashboard fills in as runs execute."
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard
          label="Overall success rate"
          value={formatPercent(summary.overall_success_rate)}
          sub={`${summary.overall_success_count} / ${summary.overall_total} invocations`}
        />
        <SummaryCard
          label="Top failure category"
          value={
            Object.entries(summary.failure_category_breakdown).sort((a, b) => b[1] - a[1])[0]?.[0]?.replace(
              /_/g,
              " ",
            ) ?? "—"
          }
        />
        <SummaryCard
          label="Top provider"
          value={Object.entries(summary.provider_breakdown).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—"}
        />
      </div>

      <div className="surface-card overflow-x-auto rounded-xl border border-border/60 p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-foreground">By agent</h2>
          <Badge variant="outline" className="text-xs text-muted-foreground">
            Sorted by failure rate first
          </Badge>
        </div>
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-border/60 text-left text-xs text-muted-foreground">
              <th className="pb-2 pl-1 font-medium">Agent</th>
              <th className="pb-2 text-right font-medium">Invocations</th>
              <th className="pb-2 text-right font-medium">Success rate</th>
              <th className="pb-2 text-right font-medium">Avg duration</th>
              <th className="pb-2 pr-1 text-right font-medium">Avg input tokens</th>
            </tr>
          </thead>
          <tbody>
            {sortedAgents.map((stats) => (
              <AgentRow key={stats.agent} stats={stats} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
