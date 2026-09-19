import { cn } from "@/lib/utils";
import type { WorkflowStatus } from "@/lib/types";

const STATUS_CONFIG: Record<
  WorkflowStatus,
  { label: string; dot: string; text: string; pulse?: boolean }
> = {
  initialized: { label: "Initialized", dot: "bg-status-pending", text: "text-muted-foreground" },
  running: { label: "Running", dot: "bg-status-running", text: "text-primary", pulse: true },
  waiting_for_user: {
    label: "Waiting",
    dot: "bg-status-pending",
    text: "text-muted-foreground",
  },
  completed: { label: "Completed", dot: "bg-status-completed", text: "text-status-completed" },
  completed_with_verification_issues: {
    label: "Verification issues",
    dot: "bg-status-warning",
    text: "text-status-warning",
  },
  failed: { label: "Failed", dot: "bg-status-failed", text: "text-status-failed" },
};

export function StatusBadge({
  status,
  className,
}: {
  status: WorkflowStatus;
  className?: string;
}) {
  const config = STATUS_CONFIG[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-surface-2/60 px-2.5 py-1 font-mono text-[10px] font-medium tracking-wide uppercase",
        config.text,
        className,
      )}
    >
      <span className="relative flex size-1.5">
        {config.pulse && (
          <span
            className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", config.dot)}
          />
        )}
        <span className={cn("relative inline-flex size-1.5 rounded-full", config.dot)} />
      </span>
      {config.label}
    </span>
  );
}
