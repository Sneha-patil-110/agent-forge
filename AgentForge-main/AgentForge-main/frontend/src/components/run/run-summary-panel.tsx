"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { FileCode2, FlaskConical, ShieldCheck, TriangleAlert } from "lucide-react";
import { getRun } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import type { WorkflowStatus } from "@/lib/types";

function testingResultLabel(result: string): string {
  switch (result) {
    case "passed":
      return "Passed";
    case "no_tests_discovered":
      return "No tests discovered";
    case "not_run":
      return "Not run";
    default:
      return result.replace(/_/g, " ");
  }
}

function isTerminal(status: WorkflowStatus | undefined) {
  return (
    status === "completed" ||
    status === "completed_with_verification_issues" ||
    status === "failed"
  );
}

export function RunSummaryPanel({ runId }: { runId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["run-detail", runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 3000),
  });

  if (isLoading || !data) {
    return (
      <div className="surface-card space-y-3 rounded-xl p-4">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="surface-card space-y-4 rounded-xl p-4"
    >
      <div>
        <h3 className="text-sm font-medium text-foreground">
          {data.project_name ?? "Project"}
        </h3>
        {data.error_message && (
          <p className="mt-2 flex items-start gap-1.5 rounded-md bg-status-failed/10 px-2.5 py-2 text-xs text-status-failed">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
            {data.error_message}
          </p>
        )}
      </div>

      <dl className="space-y-2.5 text-sm">
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <FlaskConical className="size-3.5" />
            Testing
          </dt>
          <dd className="font-medium text-foreground">
            {testingResultLabel(data.testing_result)}
            {data.testing_result === "no_tests_discovered" && data.verification_method && (
              <span className="ml-1 text-xs text-muted-foreground">
                ({data.verification_method === "none" ? "no verification available" : data.verification_method})
              </span>
            )}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            Review
          </dt>
          <dd className="font-medium text-foreground">
            {data.review_auto_passed
              ? "Passed with warnings"
              : data.review_passed
                ? "Passed"
                : "Pending"}{" "}
            · {data.review_score.toFixed(1)}/10
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            <FileCode2 className="size-3.5" />
            Files
          </dt>
          <dd className="font-medium text-foreground">{data.files_materialized}</dd>
        </div>
      </dl>

      {(data.test_retry_count > 0 || data.review_retry_count > 0 || data.dependency_retry_count > 0) && (
        <div className="flex gap-3 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          <span>{data.test_retry_count} test repair(s)</span>
          <span>{data.review_retry_count} review repair(s)</span>
          {data.dependency_retry_count > 0 && (
            <span>{data.dependency_retry_count} dependency repair(s)</span>
          )}
        </div>
      )}

      {data.review_auto_passed && (
        <div className="space-y-2 rounded-md border border-status-warning/30 bg-status-warning/10 px-2.5 py-2.5 text-xs">
          <p className="flex items-center gap-1.5 font-medium text-status-warning">
            <TriangleAlert className="size-3.5 shrink-0" />
            Reviewer rejected this repository twice ({data.review_attempt_number} attempts) and
            was auto-passed with unresolved findings
          </p>
          {data.review_summary && <p className="text-muted-foreground">{data.review_summary}</p>}
          {data.review_issues.length > 0 && (
            <ul className="space-y-1 text-muted-foreground">
              {data.review_issues.map((issue, index) => (
                <li key={`${issue.title}-${index}`} className="flex items-start gap-1.5">
                  <span className="mt-0.5 shrink-0 rounded bg-status-warning/20 px-1 py-0.5 font-mono text-[10px] uppercase text-status-warning">
                    {issue.severity}
                  </span>
                  <span>
                    {issue.title}
                    {issue.file_path && (
                      <span className="ml-1 font-mono text-[11px] text-muted-foreground/80">
                        [{issue.file_path}]
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {data.status === "completed_with_verification_issues" && (
        <div className="space-y-2 rounded-md border border-status-warning/30 bg-status-warning/10 px-2.5 py-2.5 text-xs">
          <p className="flex items-center gap-1.5 font-medium text-status-warning">
            <TriangleAlert className="size-3.5 shrink-0" />
            Verification incomplete
          </p>
          {(data.total_tests > 0 || data.failed_tests_count > 0) && (
            <p className="text-muted-foreground">
              {data.passed_tests} passed · {data.failed_tests_count} failed
              {data.total_tests > 0 ? ` of ${data.total_tests}` : ""}
            </p>
          )}
          {data.failure_classification && (
            <p className="text-muted-foreground">
              Classification: <span className="font-medium text-foreground">{data.failure_classification}</span>
            </p>
          )}
          {data.tester_summary && <p className="text-muted-foreground">{data.tester_summary}</p>}
          {data.failed_test_names.length > 0 && (
            <ul className="space-y-0.5 text-muted-foreground">
              {data.failed_test_names.slice(0, 5).map((failure) => (
                <li key={failure.name} className="truncate font-mono text-[11px]">
                  {failure.name}
                </li>
              ))}
              {data.failed_test_names.length > 5 && (
                <li className="text-[11px]">+{data.failed_test_names.length - 5} more</li>
              )}
            </ul>
          )}
        </div>
      )}
    </motion.div>
  );
}
