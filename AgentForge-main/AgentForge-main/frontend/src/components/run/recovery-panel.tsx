"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Clipboard,
  Code2,
  Copy,
  FileText,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Sparkles,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import {
  duplicateProjectAndRetry,
  getFailureDetail,
  getRunLogs,
  listCheckpoints,
  restartFromCheckpoint,
  restartProjectWorkflow,
  retryFailedAgent,
} from "@/lib/api";
import { useRecoveryProgress } from "@/hooks/use-recovery-progress";
import { ResumeButton } from "@/components/run/resume-button";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { WorkflowStatus } from "@/lib/types";

const RECOMMENDED_LABEL: Record<string, string> = {
  resume: "Resume",
  retry_agent: "Retry Failed Agent",
  restart_from_checkpoint: "Restart From Checkpoint",
  restart_workflow: "Restart Entire Workflow",
  duplicate_and_retry: "Duplicate & Retry",
};

export function RecoveryPanel({
  runId,
  projectId,
  overallStatus,
  onRecovered,
  filesHref,
  docsHref,
}: {
  runId: string;
  projectId: string | null;
  overallStatus: WorkflowStatus;
  onRecovered: () => void;
  filesHref: string;
  docsHref?: string | null;
}) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [checkpointDialogOpen, setCheckpointDialogOpen] = useState(false);
  const [logsDialogOpen, setLogsDialogOpen] = useState(false);
  const progress = useRecoveryProgress();

  const failureQuery = useQuery({
    queryKey: ["run-failure", runId],
    queryFn: () => getFailureDetail(runId),
  });

  const checkpointsQuery = useQuery({
    queryKey: ["run-checkpoints", runId],
    queryFn: () => listCheckpoints(runId),
    enabled: checkpointDialogOpen,
  });

  const logsQuery = useQuery({
    queryKey: ["run-logs", runId],
    queryFn: () => getRunLogs(runId),
    enabled: logsDialogOpen,
  });

  function invalidateAfterRecovery() {
    queryClient.invalidateQueries({ queryKey: ["runs"] });
    queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });
    queryClient.invalidateQueries({ queryKey: ["run-failure", runId] });
    queryClient.invalidateQueries({ queryKey: ["run-timeline", runId] });
  }

  const retryAgentMutation = useMutation({
    mutationFn: () => {
      progress.start(["Restoring checkpoint…", "Retrying the failed agent…", "Reconnecting…"]);
      return retryFailedAgent(runId);
    },
    onSuccess: () => {
      invalidateAfterRecovery();
      toast.success("Retrying failed agent", { description: runId });
      onRecovered();
    },
    onError: (error: Error) => toast.error("Couldn't retry", { description: error.message }),
    onSettled: () => progress.stop(),
  });

  const restartCheckpointMutation = useMutation({
    mutationFn: (checkpointId: string) => {
      progress.start(["Restoring checkpoint…", "Reloading workflow state…", "Reconnecting…"]);
      return restartFromCheckpoint(runId, checkpointId);
    },
    onSuccess: () => {
      invalidateAfterRecovery();
      setCheckpointDialogOpen(false);
      toast.success("Restarting from checkpoint", { description: runId });
      onRecovered();
    },
    onError: (error: Error) => toast.error("Couldn't restart from checkpoint", { description: error.message }),
    onSettled: () => progress.stop(),
  });

  const restartWorkflowMutation = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project to restart.");
      progress.start(["Backing up the current workspace…", "Starting a fresh workflow…"]);
      return restartProjectWorkflow(projectId);
    },
    onSuccess: (accepted) => {
      toast.success("Restarting workflow", {
        description: "Previous workspace backed up before restarting.",
      });
      router.push(`/runs/${accepted.run_id}`);
    },
    onError: (error: Error) => toast.error("Couldn't restart workflow", { description: error.message }),
    onSettled: () => progress.stop(),
  });

  const duplicateMutation = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project to duplicate.");
      progress.start(["Creating a new project…", "Starting from the original request…"]);
      return duplicateProjectAndRetry(projectId);
    },
    onSuccess: (accepted) => {
      toast.success("Duplicated as a new project", { description: accepted.project_id });
      router.push(`/projects/${accepted.project_id}`);
    },
    onError: (error: Error) => toast.error("Couldn't duplicate project", { description: error.message }),
    onSettled: () => progress.stop(),
  });

  const anyPending =
    retryAgentMutation.isPending ||
    restartCheckpointMutation.isPending ||
    restartWorkflowMutation.isPending ||
    duplicateMutation.isPending;

  function reportIssue() {
    const detail = failureQuery.data;
    const summary = [
      `Run: ${runId}`,
      detail?.failed_agent ? `Failed agent: ${detail.failed_agent}` : null,
      detail?.failure_category ? `Category: ${detail.failure_category}` : null,
      detail?.recovery_reason ? `Reason: ${detail.recovery_reason}` : null,
      detail?.error_message ? `Error: ${detail.error_message}` : null,
    ]
      .filter(Boolean)
      .join("\n");

    navigator.clipboard
      .writeText(summary)
      .then(() => toast.success("Failure summary copied to clipboard"))
      .catch(() => toast.error("Couldn't copy to clipboard"));
  }

  const detail = failureQuery.data;
  const recommendation = detail?.recommendation;

  return (
    <div className="surface-card space-y-4 rounded-xl border border-status-failed/30 p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-status-failed" />
        <div className="min-w-0 flex-1 space-y-1">
          <h3 className="text-sm font-semibold text-foreground">
            {overallStatus === "failed" ? "This run failed" : "This run was interrupted"}
          </h3>
          {detail?.error_message && <p className="text-sm text-muted-foreground">{detail.error_message}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {detail?.failed_agent && (
              <span>
                Failed agent: <span className="capitalize text-foreground/80">{detail.failed_agent}</span>
              </span>
            )}
            {detail?.last_successful_agent && (
              <span>
                Last successful step:{" "}
                <span className="capitalize text-foreground/80">{detail.last_successful_agent}</span>
              </span>
            )}
            {(detail?.test_retry_count ?? 0) > 0 && <span>Test retries: {detail?.test_retry_count}</span>}
            {(detail?.review_retry_count ?? 0) > 0 && <span>Review retries: {detail?.review_retry_count}</span>}
            {detail?.recovery_reason && (
              <span className="capitalize">Reason: {detail.recovery_reason.replace(/_/g, " ")}</span>
            )}
            {detail?.provider && (
              <span>
                Provider: {detail.provider}
                {detail.model ? ` (${detail.model})` : ""}
              </span>
            )}
          </div>
          {detail?.repeated_failure && (
            <Badge variant="outline" className="border-status-failed/40 text-status-failed">
              Same failure as the previous attempt
            </Badge>
          )}
        </div>
      </div>

      {recommendation && (
        <div className="flex items-start gap-2.5 rounded-lg border border-primary/30 bg-primary/5 p-3">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-foreground">
              Recommended: {RECOMMENDED_LABEL[recommendation.mode] ?? recommendation.mode}{" "}
              <span className="font-normal text-muted-foreground">
                ({Math.round(recommendation.confidence * 100)}% confidence)
              </span>
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">{recommendation.explanation}</p>
          </div>
        </div>
      )}

      {progress.stage && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          {progress.stage}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {overallStatus !== "failed" && <ResumeButton runId={runId} variant="default" onResumed={onRecovered} />}

        <Button
          size="sm"
          variant={recommendation?.mode === "retry_agent" ? "default" : "outline"}
          disabled={anyPending}
          isLoading={retryAgentMutation.isPending}
          className="gap-1.5"
          onClick={() => retryAgentMutation.mutate()}
        >
          {!retryAgentMutation.isPending && <RotateCcw className="size-3.5" />}
          Retry Failed Agent
        </Button>

        <Dialog open={checkpointDialogOpen} onOpenChange={setCheckpointDialogOpen}>
          <DialogTrigger asChild>
            <Button
              size="sm"
              variant={recommendation?.mode === "restart_from_checkpoint" ? "default" : "outline"}
              disabled={anyPending}
              className="gap-1.5"
            >
              <History className="size-3.5" />
              Restart From Checkpoint
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Restart from a checkpoint</DialogTitle>
              <DialogDescription>
                Picks up right after the selected step, discarding anything the run did after it.
              </DialogDescription>
            </DialogHeader>
            <div className="max-h-72 space-y-1 overflow-y-auto">
              {checkpointsQuery.isLoading && (
                <p className="text-sm text-muted-foreground">Loading checkpoints…</p>
              )}
              {checkpointsQuery.data?.checkpoints.length === 0 && (
                <p className="text-sm text-muted-foreground">No checkpoints available for this run.</p>
              )}
              {checkpointsQuery.data?.checkpoints.map((checkpoint) => (
                <button
                  key={checkpoint.checkpoint_id}
                  disabled={restartCheckpointMutation.isPending}
                  onClick={() => restartCheckpointMutation.mutate(checkpoint.checkpoint_id)}
                  className="flex w-full items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-left text-sm transition-colors hover:bg-accent/50 disabled:opacity-50"
                >
                  <span className="capitalize text-foreground/90">
                    {checkpoint.node_name?.replace("_", " ") ?? "Unknown step"}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {checkpoint.timestamp ? new Date(checkpoint.timestamp).toLocaleTimeString() : ""}
                  </span>
                </button>
              ))}
            </div>
          </DialogContent>
        </Dialog>

        {projectId && (
          <Button
            size="sm"
            variant={recommendation?.mode === "restart_workflow" ? "default" : "outline"}
            disabled={anyPending}
            className="gap-1.5"
            onClick={() => {
              if (!window.confirm("Restart the entire workflow from scratch? The current workspace will be backed up first.")) return;
              restartWorkflowMutation.mutate();
            }}
          >
            <RefreshCw className="size-3.5" />
            Restart Entire Workflow
          </Button>
        )}

        {projectId && (
          <Button
            size="sm"
            variant={recommendation?.mode === "duplicate_and_retry" ? "default" : "outline"}
            disabled={anyPending}
            className="gap-1.5"
            onClick={() => duplicateMutation.mutate()}
          >
            <Copy className="size-3.5" />
            Duplicate &amp; Retry
          </Button>
        )}

        <Dialog open={logsDialogOpen} onOpenChange={setLogsDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="outline" className="gap-1.5">
              <ScrollText className="size-3.5" />
              View Logs
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Logs for {runId}</DialogTitle>
              {logsQuery.data?.truncated && (
                <DialogDescription>Showing the most recent lines only.</DialogDescription>
              )}
            </DialogHeader>
            <div className="max-h-96 overflow-y-auto rounded-lg bg-surface-2 p-3 font-mono text-xs">
              {logsQuery.isLoading && <p className="text-muted-foreground">Loading…</p>}
              {logsQuery.data?.lines.length === 0 && (
                <p className="text-muted-foreground">No log lines found for this run.</p>
              )}
              {logsQuery.data?.lines.map((line, index) => (
                <div key={index} className="whitespace-pre-wrap break-all text-foreground/80">
                  {line}
                </div>
              ))}
            </div>
            <DialogFooter>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5"
                onClick={() => {
                  navigator.clipboard.writeText((logsQuery.data?.lines ?? []).join("\n"));
                  toast.success("Logs copied to clipboard");
                }}
              >
                <Clipboard className="size-3.5" />
                Copy
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Button asChild variant="outline" size="sm" className="gap-1.5">
          <Link href={filesHref}>
            <Code2 className="size-3.5" />
            View Generated Files
          </Link>
        </Button>

        {docsHref && (
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link href={docsHref}>
              <FileText className="size-3.5" />
              View Documentation
            </Link>
          </Button>
        )}

        <Button size="sm" variant="ghost" className="gap-1.5 text-muted-foreground" onClick={reportIssue}>
          <Zap className="size-3.5" />
          Report Issue
        </Button>
      </div>
    </div>
  );
}
