"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { eventsStreamUrl } from "@/lib/api";
import { TERMINAL_EVENT_TYPES, type WorkflowEventPayload } from "@/lib/types";
import type { ConnectionState } from "@/hooks/use-run-events";

interface RunEventsContextValue {
  events: WorkflowEventPayload[];
  connectionState: ConnectionState;
  reconnect: () => void;
}

const RunEventsContext = createContext<RunEventsContextValue | null>(null);

export function RunEventsProvider({ runId, children }: { runId: string | null; children: ReactNode }) {
  const [events, setEvents] = useState<WorkflowEventPayload[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [generation, setGeneration] = useState(0);

  useEffect(() => {
    if (!runId) {
      return;
    }

    const source = new EventSource(eventsStreamUrl(runId));

    source.onopen = () => setConnectionState("open");

    source.onmessage = (message) => {
      const payload = JSON.parse(message.data) as WorkflowEventPayload;
      setEvents((previous) => [...previous, payload]);

      if (TERMINAL_EVENT_TYPES.includes(payload.event_type)) {
        source.close();
        setConnectionState("closed");
      }
    };

    source.onerror = () => {
      setConnectionState(source.readyState === EventSource.CLOSED ? "closed" : "error");
    };

    return () => source.close();
  }, [runId, generation]);

  const reconnect = useCallback(() => {
    setEvents([]);
    setConnectionState("connecting");
    setGeneration((current) => current + 1);
  }, []);

  const value: RunEventsContextValue = useMemo(
    () =>
      runId
        ? { events, connectionState, reconnect }
        : { events: [], connectionState: "closed" as ConnectionState, reconnect },
    [runId, events, connectionState, reconnect],
  );

  return <RunEventsContext.Provider value={value}>{children}</RunEventsContext.Provider>;
}

export function useSharedRunEvents(): RunEventsContextValue {
  const context = useContext(RunEventsContext);

  if (!context) {
    throw new Error("useSharedRunEvents must be used within a RunEventsProvider");
  }

  return context;
}
