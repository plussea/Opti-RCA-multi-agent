"use client";

import { useEffect, useRef, useState } from "react";
import { getSSEUrl } from "~/lib/api";
import { useSessionStore } from "~/store/sessionStore";
import type { Session } from "~/lib/types";

interface UseSSEOptions {
  sessionId: string | null;
}

export function useSSE({ sessionId }: UseSSEOptions) {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const { updateActive } = useSessionStore();

  useEffect(() => {
    if (!sessionId) return;

    const es = new EventSource(getSSEUrl(sessionId));
    esRef.current = es;
    setConnected(true);
    setError(null);

    es.addEventListener("status", (e) => {
      try {
        const data: Session = JSON.parse(e.data);
        updateActive(data);
      } catch {
        // ignore parse errors during reconnection
      }
    });

    es.addEventListener("error", (e) => {
      const target = e.target as EventSource;
      if (target.readyState === EventSource.CLOSED) {
        setConnected(false);
      }
    });

    es.onerror = () => {
      // EventSource auto-reconnects; mark as disconnected briefly
      setConnected(false);
      setError("Connection lost, reconnecting...");
      // Clear error after a moment since SSE reconnects automatically
      setTimeout(() => setError(null), 3000);
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [sessionId, updateActive]);

  return { connected, error };
}
