"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Check, X } from "lucide-react";
import { getWorkflowGraph } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  FALLBACK_AGENT_PIPELINE,
  type AgentType,
  type WorkflowEventPayload,
  type WorkflowStatus,
} from "@/lib/types";

type NodeState = "pending" | "active" | "completed" | "failed";

const AGENT_LABELS: Partial<Record<AgentType, string>> = {
  analysis: "Analysis",
  planner: "Planner",
  architect: "Architect",
  developer: "Developer",
  static_validation: "Validate",
  tester: "Tester",
  debugger: "Debugger",
  reviewer: "Reviewer",
  documentation: "Docs",
};

function labelFor(agent: AgentType): string {
  const known = AGENT_LABELS[agent];
  if (known) return known;
  return agent
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function deriveStates(
  pipeline: AgentType[],
  events: WorkflowEventPayload[],
  overallStatus: WorkflowStatus,
): Record<string, NodeState> {
  const order = new Map(pipeline.map((agent, index) => [agent, index]));
  const states: Record<string, NodeState> = Object.fromEntries(
    pipeline.map((agent) => [agent, "pending" as NodeState]),
  );

  let lastActive: AgentType | null = null;

  for (const event of events) {
    if (!event.agent) continue;

    const index = order.get(event.agent);
    if (index === undefined) continue;

    if (event.event_type === "agent_started") {
      for (let i = index; i < pipeline.length; i += 1) {
        states[pipeline[i]] = i === index ? "active" : "pending";
      }
      lastActive = event.agent;
    } else if (event.event_type === "agent_completed") {
      states[event.agent] = "completed";
      if (lastActive === event.agent) lastActive = null;
    }
  }

  if (
    (overallStatus === "failed" || overallStatus === "completed_with_verification_issues") &&
    lastActive
  ) {
    states[lastActive] = "failed";
  }

  return states;
}

export function AgentPipeline({
  events,
  overallStatus,
}: {
  events: WorkflowEventPayload[];
  overallStatus: WorkflowStatus;
}) {
  const graphQuery = useQuery({
    queryKey: ["workflow-graph"],
    queryFn: () => getWorkflowGraph(),
    staleTime: Infinity,
  });

  const pipeline = graphQuery.data?.nodes ?? FALLBACK_AGENT_PIPELINE;
  const states = useMemo(
    () => deriveStates(pipeline, events, overallStatus),
    [pipeline, events, overallStatus],
  );

  return (
    <div className="surface-card overflow-x-auto rounded-xl p-5">
      <div className="flex min-w-max items-center">
        {pipeline.map((agent, index) => {
          const state = states[agent];
          const isLast = index === pipeline.length - 1;

          return (
            <div key={agent} className="flex items-center">
              <div className="flex flex-col items-center gap-2">
                <motion.div
                  layout
                  animate={{
                    scale: state === "active" ? 1.08 : 1,
                  }}
                  transition={{ type: "spring", stiffness: 300, damping: 20 }}
                  className={cn(
                    "relative flex size-9 items-center justify-center rounded-full border text-xs font-semibold transition-colors",
                    state === "pending" &&
                      "border-border bg-surface-2 text-muted-foreground",
                    state === "active" &&
                      "glow-ember border-primary bg-primary text-primary-foreground",
                    state === "completed" &&
                      "border-status-completed/40 bg-status-completed/15 text-status-completed",
                    state === "failed" &&
                      "border-status-failed/40 bg-status-failed/15 text-status-failed",
                  )}
                >
                  {state === "active" && (
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/50" />
                  )}
                  <span className="relative">
                    {state === "completed" ? (
                      <Check className="size-4" />
                    ) : state === "failed" ? (
                      <X className="size-4" />
                    ) : (
                      index + 1
                    )}
                  </span>
                </motion.div>
                <span
                  className={cn(
                    "text-xs font-medium",
                    state === "pending" ? "text-muted-foreground" : "text-foreground",
                  )}
                >
                  {labelFor(agent)}
                </span>
              </div>

              {!isLast && (
                <div className="mx-2 h-px w-10 shrink-0 overflow-hidden bg-border sm:w-14">
                  <motion.div
                    initial={{ width: "0%" }}
                    animate={{ width: state === "completed" ? "100%" : "0%" }}
                    transition={{ duration: 0.4, ease: "easeOut" }}
                    className="h-full bg-status-completed/60"
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
