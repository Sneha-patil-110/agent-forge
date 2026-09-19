"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { ApiError, resumeRun } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ResumeButton({
  runId,
  size = "sm",
  variant = "outline",
  className,
  onResumed,
}: {
  runId: string;
  size?: "xs" | "sm" | "default";
  variant?: "outline" | "default" | "secondary";
  className?: string;
  onResumed?: () => void;
}) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => resumeRun(runId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["run-detail", runId] });

      if (data.status === "running") {
        toast.success("Resuming run", { description: runId });
      } else {
        toast.info("This run already finished", {
          description: "Nothing to resume, refreshing its status.",
        });
      }

      onResumed?.();
    },
    onError: (error: Error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.info("Already resuming", { description: "This run is already being resumed." });
        return;
      }
      toast.error("Couldn't resume run", { description: error.message });
    },
  });

  return (
    <Button
      size={size}
      variant={variant}
      isLoading={mutation.isPending}
      className={cn("gap-1.5", className)}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!mutation.isPending) mutation.mutate();
      }}
    >
      {!mutation.isPending && <RotateCcw className="size-3.5" />}
      Resume
    </Button>
  );
}
