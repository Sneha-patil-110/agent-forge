"use client";

import { useMemo } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowLeft, Code2, LayoutDashboard } from "lucide-react";
import { getRun } from "@/lib/api";
import { useRunEvents } from "@/hooks/use-run-events";
import { AgentPipeline } from "@/components/run/agent-pipeline";
import { EventFeed } from "@/components/run/event-feed";
import { RunSummaryPanel } from "@/components/run/run-summary-panel";
import { StatusBadge } from "@/components/run/status-badge";
import { ResumeButton } from "@/components/run/resume-button";
import { RecoveryPanel } from "@/components/run/recovery-panel";
import { RepoExplorer } from "@/components/repo/repo-explorer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isResumableStatus, type WorkflowStatus } from "@/lib/types";

function deriveOverallStatus(
  events: ReturnType<typeof useRunEvents>["events"],
): WorkflowStatus {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const type = events[i].event_type;
    if (type === "workflow_completed") return "completed";
    if (type === "workflow_failed") return "failed";
    if (type === "workflow_interrupted") return "waiting_for_user";
  }
  return events.length > 0 ? "running" : "initialized";
}

const VALID_TABS = new Set(["activity", "code"]);

export function RunView({ runId }: { runId: string }) {
  const { events, connectionState, reconnect } = useRunEvents(runId);
  const overallStatus = useMemo(() => deriveOverallStatus(events), [events]);
  const runDetailQuery = useQuery({ queryKey: ["run-detail", runId], queryFn: () => getRun(runId) });

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const activeTab = requestedTab && VALID_TABS.has(requestedTab) ? requestedTab : "activity";

  function setActiveTab(tab: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === "activity") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function handleResumed() {
    if (connectionState === "closed") reconnect();
  }

  const needsRecovery = overallStatus === "failed" || overallStatus === "waiting_for_user";
  const showHeaderResume =
    isResumableStatus(overallStatus) && (overallStatus !== "running" || connectionState !== "open");

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex h-full min-h-0 flex-col gap-6"
    >
      <div>
        <Link
          href="/"
          className="mb-3 inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          All runs
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-mono text-lg text-foreground">{runId}</h1>
          <StatusBadge status={overallStatus} />
          {showHeaderResume && <ResumeButton runId={runId} onResumed={handleResumed} />}
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="min-h-0 flex-1">
        <TabsList>
          <TabsTrigger value="activity" className="gap-1.5">
            <LayoutDashboard className="size-3.5" />
            Activity
          </TabsTrigger>
          <TabsTrigger value="code" className="gap-1.5">
            <Code2 className="size-3.5" />
            Code
          </TabsTrigger>
        </TabsList>

        <TabsContent value="activity" className="flex flex-col gap-4">
          {needsRecovery && (
            <RecoveryPanel
              runId={runId}
              projectId={runDetailQuery.data?.project_id ?? null}
              overallStatus={overallStatus}
              onRecovered={handleResumed}
              filesHref={`/runs/${runId}?tab=code`}
            />
          )}
          <AgentPipeline events={events} overallStatus={overallStatus} />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_18rem]">
            <EventFeed events={events} connectionState={connectionState} />
            <RunSummaryPanel runId={runId} />
          </div>
        </TabsContent>

        <TabsContent value="code" className="min-h-0 flex-1 overflow-hidden">
          <RepoExplorer runId={runId} events={events} />
        </TabsContent>
      </Tabs>
    </motion.div>
  );
}
