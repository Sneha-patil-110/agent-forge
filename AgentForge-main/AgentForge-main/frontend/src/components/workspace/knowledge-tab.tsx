"use client";

import { useQuery } from "@tanstack/react-query";
import { Lightbulb, TriangleAlert } from "lucide-react";
import { listKnowledge } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";

const CATEGORY_LABELS: Record<string, string> = {
  architecture_decision: "Architecture Decision",
  technology_stack: "Technology Stack",
  project_convention: "Project Convention",
  api_decision: "API Decision",
  database_decision: "Database Decision",
  coding_standard: "Coding Standard",
  assumption: "Assumption",
  known_limitation: "Known Limitation",
  completed_milestone: "Completed Milestone",
};

export function KnowledgeTab({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ["knowledge", runId],
    queryFn: () => listKnowledge(runId),
  });

  if (query.isLoading) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-status-failed">
        <TriangleAlert className="size-4" />
        Couldn&apos;t load project knowledge.
      </div>
    );
  }

  const entries = query.data?.entries ?? [];

  if (entries.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
        <Lightbulb className="size-6 opacity-50" />
        No project knowledge recorded yet.
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto p-4">
      <ul className="space-y-2.5">
        {entries.map((entry) => (
          <li key={entry.id} className="surface-card rounded-lg p-3">
            <div className="mb-1 flex items-center gap-2">
              <Lightbulb className="size-3.5 shrink-0 text-primary" />
              <span className="text-xs font-medium text-muted-foreground">
                {CATEGORY_LABELS[entry.category] ?? entry.category}
              </span>
            </div>
            <p className="text-sm font-medium text-foreground">{entry.title}</p>
            <p className="mt-0.5 text-sm text-muted-foreground">{entry.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
