"use client";

import { useEffect, useRef, useState } from "react";
import { eventsStreamUrl } from "@/lib/api";
import { TERMINAL_EVENT_TYPES, type WorkflowEventPayload } from "@/lib/types";

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export function useRunEvents(runId: string) {
  const [events, setEvents] = useState<WorkflowEventPayload[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [generation, setGeneration] = useState(0);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const source = new EventSource(eventsStreamUrl(runId));
    sourceRef.current = source;

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
      if (source.readyState === EventSource.CLOSED) {
        setConnectionState("closed");
      } else {
        setConnectionState("error");
      }
    };

    return () => {
      source.close();
    };
  }, [runId, generation]);

  function reconnect() {
    setEvents([]);
    setConnectionState("connecting");
    setGeneration((current) => current + 1);
  }

  return { events, connectionState, reconnect };
}
