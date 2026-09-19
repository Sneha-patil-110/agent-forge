"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  BookOpen,
  Code2,
  FolderTree,
  LayoutDashboard,
  MessageSquare,
  Pencil,
  RotateCcw,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { deleteProject, getProjectDetail, renameProject } from "@/lib/api";
import { RunEventsProvider, useSharedRunEvents } from "@/hooks/use-run-events-context";
import { ChatPanel } from "@/components/chat/chat-panel";
import { AgentPipeline } from "@/components/run/agent-pipeline";
import { EventFeed } from "@/components/run/event-feed";
import { RecoveryPanel } from "@/components/run/recovery-panel";
import { WorkflowTimeline } from "@/components/run/workflow-timeline";
import { StatusBadge } from "@/components/run/status-badge";
import { RepoExplorer } from "@/components/repo/repo-explorer";
import { DocumentationTab } from "@/components/workspace/documentation-tab";
import { KnowledgeTab } from "@/components/workspace/knowledge-tab";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { WorkflowStatus } from "@/lib/types";

const ACTIVE_STATUSES = new Set(["initialized", "running", "waiting_for_user"]);
const VALID_TABS = new Set(["chat", "repository", "activity", "documentation", "knowledge"]);

function ActivityTab({
  runId,
  projectId,
  status,
}: {
  runId: string;
  projectId: string;
  status: WorkflowStatus;
}) {
  const { events, connectionState, reconnect } = useSharedRunEvents();
  const needsRecovery = status === "failed" || status === "waiting_for_user";

  return (
    <div className="flex flex-col gap-4 p-1">
      {needsRecovery && (
        <RecoveryPanel
          runId={runId}
          projectId={projectId}
          overallStatus={status}
          onRecovered={() => {
            if (connectionState === "closed") reconnect();
          }}
          filesHref={`/projects/${projectId}?tab=repository`}
          docsHref={`/projects/${projectId}?tab=documentation`}
        />
      )}
      <AgentPipeline events={events} overallStatus={status} />
      <WorkflowTimeline runId={runId} />
      <EventFeed events={events} connectionState={connectionState} />
    </div>
  );
}

function RepositoryTab({ runId, projectId }: { runId: string; projectId: string }) {
  const { events } = useSharedRunEvents();
  return <RepoExplorer runId={runId} events={events} storageKey={projectId} />;
}

function ProjectTitle({ projectId, name }: { projectId: string; name: string | null }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name ?? "");

  const renameMutation = useMutation({
    mutationFn: (newName: string) => renameProject(projectId, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-detail", projectId] });
      setEditing(false);
    },
  });

  if (editing) {
    return (
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const trimmed = value.trim();
          if (trimmed) renameMutation.mutate(trimmed);
        }}
        className="flex items-center gap-2"
      >
        <input
          autoFocus
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onBlur={() => setEditing(false)}
          className="rounded-md border border-border/60 bg-background px-2 py-1 text-lg text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </form>
    );
  }

  return (
    <button
      onClick={() => {
        setValue(name ?? "");
        setEditing(true);
      }}
      className="group flex items-center gap-1.5 text-lg text-foreground"
    >
      {name ?? "Untitled project"}
      <Pencil className="size-3.5 opacity-0 transition-opacity group-hover:opacity-60" />
    </button>
  );
}

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const activeTab = requestedTab && VALID_TABS.has(requestedTab) ? requestedTab : "chat";

  const projectQuery = useQuery({
    queryKey: ["project-detail", projectId],
    queryFn: () => getProjectDetail(projectId),
    refetchInterval: (query) => (ACTIVE_STATUSES.has(query.state.data?.status ?? "") ? 4000 : false),
  });

  function setActiveTab(tab: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === "chat") {
      params.delete("tab");
    } else {
      params.set("tab", tab);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  function handleDelete() {
    if (!window.confirm("Delete this project? This cannot be undone.")) return;
    deleteProject(projectId).then(() => router.push("/"));
  }

  if (projectQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border/60 p-6 text-sm text-status-failed">
        <TriangleAlert className="size-4 shrink-0" />
        <span className="flex-1">
          Couldn&apos;t load this project. The backend may still be starting up.
        </span>
        <Button variant="outline" size="xs" className="gap-1" onClick={() => projectQuery.refetch()}>
          <RotateCcw className="size-3" />
          Retry
        </Button>
      </div>
    );
  }

  const project = projectQuery.data;
  const runId = project.latest_run_id;

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
          All projects
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <ProjectTitle projectId={projectId} name={project.name} />
            <StatusBadge status={project.status as WorkflowStatus} />
            <span className="text-xs text-muted-foreground">
              {project.run_count} run{project.run_count !== 1 ? "s" : ""}
            </span>
          </div>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground hover:text-status-failed" onClick={handleDelete}>
            <Trash2 className="size-3.5" />
            Delete
          </Button>
        </div>
      </div>

      <RunEventsProvider key={runId} runId={runId}>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="min-h-0 flex-1">
          <TabsList>
            <TabsTrigger value="chat" className="gap-1.5">
              <MessageSquare className="size-3.5" />
              Chat
            </TabsTrigger>
            <TabsTrigger value="repository" className="gap-1.5">
              <FolderTree className="size-3.5" />
              Repository
            </TabsTrigger>
            <TabsTrigger value="activity" className="gap-1.5">
              <LayoutDashboard className="size-3.5" />
              Activity
            </TabsTrigger>
            <TabsTrigger value="documentation" className="gap-1.5">
              <BookOpen className="size-3.5" />
              Docs
            </TabsTrigger>
            <TabsTrigger value="knowledge" className="gap-1.5">
              <Code2 className="size-3.5" />
              Knowledge
            </TabsTrigger>
          </TabsList>

          <TabsContent value="chat" className="min-h-0 flex-1 overflow-hidden">
            <div className="surface-card h-full min-h-0 overflow-hidden rounded-xl">
              <ChatPanel projectId={projectId} project={project} />
            </div>
          </TabsContent>

          <TabsContent value="repository" className="min-h-0 flex-1 overflow-hidden">
            {runId ? (
              <RepositoryTab key={runId} runId={runId} projectId={projectId} />
            ) : (
              <EmptyRunState />
            )}
          </TabsContent>

          <TabsContent value="activity" className="min-h-0 flex-1 overflow-y-auto">
            {runId ? (
              <ActivityTab
                key={runId}
                runId={runId}
                projectId={projectId}
                status={project.status as WorkflowStatus}
              />
            ) : (
              <EmptyRunState />
            )}
          </TabsContent>

          <TabsContent value="documentation" className="min-h-0 flex-1 overflow-hidden">
            {runId ? <DocumentationTab key={runId} runId={runId} /> : <EmptyRunState />}
          </TabsContent>

          <TabsContent value="knowledge" className="min-h-0 flex-1 overflow-hidden">
            {runId ? <KnowledgeTab key={runId} runId={runId} /> : <EmptyRunState />}
          </TabsContent>
        </Tabs>
      </RunEventsProvider>
    </motion.div>
  );
}

function EmptyRunState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
      Setting up your project…
    </div>
  );
}
