"use client";

import { useEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  CheckCircle2,
  CircleDot,
  FileText,
  FlaskConical,
  Play,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { describeEvent } from "@/lib/event-labels";
import type { WorkflowEventPayload } from "@/lib/types";
import type { ConnectionState } from "@/hooks/use-run-events";

const EVENT_ICON: Record<string, React.ElementType> = {
  workflow_started: Play,
  workflow_resumed: Play,
  agent_started: Bot,
  agent_completed: CheckCircle2,
  testing_passed: FlaskConical,
  testing_failed: FlaskConical,
  review_passed: ShieldCheck,
  review_failed: ShieldCheck,
  reviewer_attempt_started: ShieldCheck,
  reviewer_attempt_completed: ShieldCheck,
  reviewer_repair_requested: ShieldCheck,
  reviewer_auto_passed: ShieldAlert,
  workflow_completed: CheckCircle2,
  workflow_interrupted: XCircle,
  workflow_failed: XCircle,
  mcp_tool_call_started: Wrench,
  mcp_tool_call_completed: Wrench,
  mcp_tool_call_failed: Wrench,
};

const FAILURE_EVENTS = new Set([
  "testing_failed",
  "review_failed",
  "workflow_failed",
  "workflow_interrupted",
  "mcp_tool_call_failed",
]);

const SUCCESS_EVENTS = new Set([
  "agent_completed",
  "testing_passed",
  "review_passed",
  "workflow_completed",
  "mcp_tool_call_completed",
]);

const WARNING_EVENTS = new Set(["reviewer_auto_passed"]);

function ConnectionIndicator({ state }: { state: ConnectionState }) {
  const config = {
    connecting: { label: "Connecting", color: "text-muted-foreground" },
    open: { label: "Live", color: "text-status-completed" },
    closed: { label: "Closed", color: "text-muted-foreground" },
    error: { label: "Reconnecting", color: "text-status-failed" },
  }[state];

  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", config.color)}>
      <Radio className="size-3" />
      {config.label}
    </span>
  );
}

export function EventFeed({
  events,
  connectionState,
}: {
  events: WorkflowEventPayload[];
  connectionState: ConnectionState;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const visibleEvents = useMemo(
    () => events.filter((event) => event.event_type !== "agent_invocation_recorded"),
    [events],
  );

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [visibleEvents.length]);

  return (
    <div className="surface-card flex h-full flex-col rounded-xl">
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <h3 className="text-sm font-medium text-foreground">Live activity</h3>
        <ConnectionIndicator state={connectionState} />
      </div>
      <div ref={scrollRef} className="max-h-96 flex-1 overflow-y-auto px-4 py-3">
        {visibleEvents.length === 0 ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <CircleDot className="size-3.5 animate-pulse" />
            Waiting for the workflow to start…
          </div>
        ) : (
          <ul className="space-y-0.5">
            <AnimatePresence initial={false}>
              {visibleEvents.map((event, index) => {
                const Icon = EVENT_ICON[event.event_type] ?? FileText;
                const isFailure = FAILURE_EVENTS.has(event.event_type);
                const isSuccess = SUCCESS_EVENTS.has(event.event_type);
                const isWarning = WARNING_EVENTS.has(event.event_type);

                return (
                  <motion.li
                    key={`${event.event_type}-${event.timestamp}-${index}`}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-accent/50"
                  >
                    <Icon
                      className={cn(
                        "mt-0.5 size-3.5 shrink-0",
                        isFailure && "text-status-failed",
                        isWarning && "text-status-warning",
                        isSuccess && !isFailure && !isWarning && "text-status-completed",
                        !isFailure && !isSuccess && !isWarning && "text-muted-foreground",
                      )}
                    />
                    <span className="flex-1 text-foreground/90">{describeEvent(event)}</span>
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </div>
  );
}
