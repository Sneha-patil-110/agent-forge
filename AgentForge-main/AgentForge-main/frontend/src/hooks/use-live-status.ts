"use client";

import { useEffect, useRef, useState } from "react";
import { describeEventAsStatus } from "@/lib/event-labels";
import { TERMINAL_EVENT_TYPES, type WorkflowEventPayload } from "@/lib/types";

export function useLiveStatusFromEvents(
  events: WorkflowEventPayload[],
  onTerminal: () => void,
): string | null {
  const [label, setLabel] = useState<string | null>(null);
  const processedCountRef = useRef(0);

  useEffect(() => {
    if (events.length === 0) {
      processedCountRef.current = 0;
      return;
    }

    for (let index = processedCountRef.current; index < events.length; index += 1) {
      const payload = events[index];
      setLabel(describeEventAsStatus(payload));

      if (TERMINAL_EVENT_TYPES.includes(payload.event_type)) {
        onTerminal();
      }
    }

    processedCountRef.current = events.length;
  }, [events, onTerminal]);

  return label;
}
