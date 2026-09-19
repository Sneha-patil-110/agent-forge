"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useRecoveryProgress(intervalMs = 1100) {
  const [stage, setStage] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setStage(null);
  }, []);

  const start = useCallback(
    (stages: string[]) => {
      stop();

      if (stages.length === 0) return;

      let index = 0;
      setStage(stages[0]);

      timerRef.current = setInterval(() => {
        index = Math.min(index + 1, stages.length - 1);
        setStage(stages[index]);

        if (index === stages.length - 1 && timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }
      }, intervalMs);
    },
    [intervalMs, stop],
  );

  useEffect(() => stop, [stop]);

  return { stage, start, stop };
}
