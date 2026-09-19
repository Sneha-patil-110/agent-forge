import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/run/status-badge";
import { ResumeButton } from "@/components/run/resume-button";
import { isResumableStatus, type ProjectSummaryOut, type WorkflowStatus } from "@/lib/types";

export function ProjectCard({ project }: { project: ProjectSummaryOut }) {
  const status = project.status as WorkflowStatus;
  const queryClient = useQueryClient();
  const canResume = isResumableStatus(status) && Boolean(project.latest_run_id);

  return (
    <Link
      href={`/projects/${project.id}`}
      className="surface-card group flex items-center justify-between gap-4 rounded-xl px-5 py-4 transition-colors hover:border-primary/30 hover:bg-surface-2/60"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <span className="truncate text-base font-medium text-foreground">
            {project.name ?? "Untitled project"}
          </span>
          <StatusBadge status={status} />
        </div>
        <p className="mt-1.5 truncate font-mono text-[11px] tracking-tight text-muted-foreground/80 tabular-nums">
          {project.run_count} run{project.run_count !== 1 ? "s" : ""} · updated{" "}
          {formatDistanceToNow(new Date(project.updated_at), { addSuffix: true })}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {canResume && project.latest_run_id && (
          <ResumeButton
            runId={project.latest_run_id}
            size="xs"
            variant="secondary"
            onResumed={() => {
              queryClient.invalidateQueries({ queryKey: ["dashboard-projects"] });
              queryClient.invalidateQueries({ queryKey: ["projects"] });
            }}
          />
        )}
        <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
      </div>
    </Link>
  );
}
